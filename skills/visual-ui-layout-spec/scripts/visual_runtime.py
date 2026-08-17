#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0.0"]
# ///
"""Visual Runtime：OpenAI-compatible 远端 VLM adapter（零配置）。

不读取任何配置文件，也不判定宿主能力。语义轨的选择规则在 SKILL.md：

  VISUAL_REMOTE=true  → 一律走本脚本（远端 VLM）
  否则                → Agent 优先用原生视觉；无视觉且远端未配置时，
                        明确告知用户无法进行视觉语义分析

远端仅需 VISUAL_BASE_URL / VISUAL_MODEL / VISUAL_API_KEY 三个环境变量。
内置：发送前降采样 + JPEG 压缩、429 退避重试、模型 JSON 输出自动修复
（围栏剥离/尾逗号/CJK 未转义引号）、可选 normalize。

用法：uv run scripts/visual_runtime.py remote-analyze <图片...> --prompt-file ...
"""
from __future__ import annotations
import argparse, base64, io, json, mimetypes, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024
SUPPORTED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


class RateLimitError(Exception):
    """429 限流，可携带 Retry-After 秒数。"""


def remote_env_state():
    """读三个 VISUAL_* 环境变量。缺失时给出可直接照做的配置指引并退出。"""
    missing = [v for v in ('VISUAL_BASE_URL', 'VISUAL_MODEL', 'VISUAL_API_KEY') if not os.getenv(v, '').strip()]
    if missing:
        print('缺少视觉模型环境变量: ' + ', '.join(missing), file=sys.stderr)
        print('请在 ~/.zshrc（或对应 shell 配置）中添加并重启终端/DSH 宿主：', file=sys.stderr)
        print('  export VISUAL_BASE_URL=https://open.bigmodel.cn/api/paas/v4', file=sys.stderr)
        print('  export VISUAL_MODEL=glm-4.6v-flash', file=sys.stderr)
        print('  export VISUAL_API_KEY=<你的Key>', file=sys.stderr)
        raise SystemExit(2)
    return os.getenv('VISUAL_BASE_URL').rstrip('/'), os.getenv('VISUAL_MODEL'), os.getenv('VISUAL_API_KEY')


def validate_image_file(path, max_bytes=DEFAULT_MAX_IMAGE_BYTES):
    """预检：存在性、大小、MIME 白名单。失败抛 SystemExit。"""
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"图片文件不存在: {p}")
    size = p.stat().st_size
    if size == 0:
        raise SystemExit(f"图片文件为空: {p}")
    if size > max_bytes:
        raise SystemExit(f"图片文件过大: {p} ({size} bytes > {max_bytes} bytes)。请先压缩或使用 image_probe.py crop 切分。")
    mime = mimetypes.guess_type(p.name)[0] or ''
    if mime.lower() not in SUPPORTED_IMAGE_MIMES:
        raise SystemExit(f"图片 MIME 不支持: {mime}（{p}）。支持的类型: {sorted(SUPPORTED_IMAGE_MIMES)}")
    return mime.lower(), size


def downscale_image(path, max_dim=1568, quality=85):
    """降采样大图 + JPEG 压缩，显著减少上行 token 和 VLM 解码开销。

    返回 (mime, bytes, orig_width, orig_height)。
    - 已是 JPEG 且尺寸 <= max_dim：原样返回（不重复压缩）。
    - 其它：转 RGB、按比例缩小到 max_dim 内、JPEG quality 压缩。

    延迟 import PIL，使纯逻辑测试无需 Pillow。
    """
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path))
    orig_w, orig_h = im.size
    name_ext = Path(path).suffix.lower()
    if max(orig_w, orig_h) <= max_dim and name_ext in ('.jpg', '.jpeg'):
        return 'image/jpeg', Path(path).read_bytes(), orig_w, orig_h
    im = im.convert('RGB')
    if max(orig_w, orig_h) > max_dim:
        ratio = max_dim / max(orig_w, orig_h)
        im = im.resize((round(orig_w * ratio), round(orig_h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=quality)
    return 'image/jpeg', buf.getvalue(), orig_w, orig_h




# --------------------------------------------------------------------------- #
# Remote VLM Adapter
# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #
# JSON 提取（含 VLM 常见瑕疵自动修复）
# --------------------------------------------------------------------------- #

def _repair_json_candidates(s):
    """按侵入性从低到高产出修复候选：尾逗号、CJK 语境未转义的 ASCII 双引号。"""
    yield s
    no_trailing = re.sub(r',\s*([}\]])', r'\1', s)
    if no_trailing != s:
        yield no_trailing
    def _quote(m):
        return m.group(1) + '\u201c' + m.group(2) + '\u201d' + m.group(3)
    quoted = re.sub(
        r'([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])\u0022([^"\n]{1,80}?)\u0022([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])',
        _quote, s)
    if quoted != s:
        yield re.sub(r',\s*([}\]])', r'\1', quoted)


def extract_json_text(text):
    s = text.strip()
    if s.startswith('```'):
        lines = s.splitlines()
        if lines and lines[0].startswith('```'): lines = lines[1:]
        if lines and lines[-1].strip() == '```': lines = lines[:-1]
        s = '\n'.join(lines).strip()
    if not s.startswith('{'):
        i, j = s.find('{'), s.rfind('}')
        if i != -1 and j > i:
            s = s[i:j + 1]
    for cand in _repair_json_candidates(s):
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _normalize_bbox(bbox, width, height):
    """各种 bbox 格式 → {x,y,width,height} 原图像素对象。无法识别原样返回。

    支持：
    - dict: {x,y,width,height} 或 {x1,y1,x2,y2}
    - list[4]: 像素 [x,y,w,h] 或 [x1,y1,x2,y2]；归一化 [x,y,w,h]（0-1 或 0-1000）
    - 多边形 [[x,y],...]：转最小外接矩形
    - 其它：原样返回
    归一化判别：0-1 可靠；0-1000 仅在值明显非整数或超出画布时采用，避免误判像素坐标。
    """
    if bbox is None:
        return None
    if isinstance(bbox, dict):
        if all(k in bbox for k in ('x', 'y', 'width', 'height')):
            try:
                return {k: round(float(bbox[k])) for k in ('x', 'y', 'width', 'height')}
            except (TypeError, ValueError):
                return bbox
        if all(k in bbox for k in ('x1', 'y1', 'x2', 'y2')):
            try:
                return {'x': round(float(bbox['x1'])), 'y': round(float(bbox['y1'])),
                        'width': round(float(bbox['x2']) - float(bbox['x1'])),
                        'height': round(float(bbox['y2']) - float(bbox['y1']))}
            except (TypeError, ValueError):
                return bbox
        return bbox
    if isinstance(bbox, list) and bbox:
        # 多边形：元素是 2 元素 list/tuple → 转最小外接矩形
        if all(isinstance(p, (list, tuple)) and len(p) == 2 for p in bbox):
            try:
                xs = [float(p[0]) for p in bbox]
                ys = [float(p[1]) for p in bbox]
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                return {'x': round(x0), 'y': round(y0),
                        'width': round(x1 - x0), 'height': round(y1 - y0)}
            except (TypeError, ValueError):
                return bbox
        if len(bbox) == 4:
            try:
                vals = [float(v) for v in bbox]
            except (TypeError, ValueError):
                return bbox
            mx = max(vals)
            is_int = all(float(v).is_integer() for v in vals)
            if width and height:
                if mx <= 1.0:  # 0–1 归一化（可靠）
                    vals = [vals[0] * width, vals[1] * height, vals[2] * width, vals[3] * height]
                elif mx <= 1000.5 and (not is_int or vals[0] + vals[2] > width or vals[1] + vals[3] > height):
                    # 0–1000 归一化：值带小数，或明显超出画布（像素坐标不可能这么高）
                    vals = [vals[0] / 1000 * width, vals[1] / 1000 * height,
                            vals[2] / 1000 * width, vals[3] / 1000 * height]
            # 启发式：[x,y,w,h]；若 w/h 明显超出画布则当作 [x1,y1,x2,y2]
            if width and vals[2] > width:
                vals[2], vals[3] = vals[2] - vals[0], vals[3] - vals[1]
            return {'x': round(vals[0]), 'y': round(vals[1]), 'width': round(vals[2]), 'height': round(vals[3])}
    return bbox


def normalize_result(data, width=None, height=None, image_type=None):
    """把 VLM 输出规范化到 image-understanding.schema.json 结构。

    处理：
    - 补 image 对象（width/height/type）；
    - 补 degradation 对象；
    - id 数字→字符串；
    - bbox 多种格式→{x,y,width,height} 像素；
    - relations 补 id、source/target→字符串；
    - 补缺失顶层字段。
    返回规范化后的 dict（原对象被就地修改并返回）。
    """
    if not isinstance(data, dict):
        return data
    # image
    img = data.get('image')
    if not isinstance(img, dict):
        img = {}
    itype = image_type or data.get('image_type') or img.get('type') or 'UNKNOWN'
    # 原图真实尺寸优先，强制覆盖 VLM 自报值（VLM 自报画布可能不准，导致 bbox 坐标错位）
    if width:
        img['width'] = int(width)
    elif img.get('width') is None:
        img['width'] = img.get('w')
    if height:
        img['height'] = int(height)
    elif img.get('height') is None:
        img['height'] = img.get('h')
    img['type'] = itype
    data['image'] = img
    # degradation
    if not isinstance(data.get('degradation'), dict):
        data['degradation'] = {'degraded': False}
    # 元素组
    for group in ('regions', 'text_blocks', 'objects'):
        arr = data.get(group)
        if not isinstance(arr, list):
            data[group] = []
            continue
        for e in arr:
            if not isinstance(e, dict):
                continue
            if 'id' in e and not isinstance(e['id'], str):
                e['id'] = str(e['id'])
            if 'bbox' in e:
                nb = _normalize_bbox(e['bbox'], img.get('width'), img.get('height'))
                if nb is not None:
                    e['bbox'] = nb
    # relations
    rels = data.get('relations')
    if not isinstance(rels, list):
        data['relations'] = []
    else:
        for i, r in enumerate(rels):
            if not isinstance(r, dict):
                continue
            if not r.get('id'):
                r['id'] = f'REL-{i + 1:03d}'
            elif not isinstance(r['id'], str):
                r['id'] = str(r['id'])
            for k in ('source', 'target'):
                if k in r and not isinstance(r[k], str):
                    r[k] = str(r[k])
        data['relations'] = rels
    # 补缺失顶层
    data.setdefault('summary', data.get('summary') or '')
    for k in ('tables', 'charts', 'diagrams', 'uncertainties'):
        data.setdefault(k, [])
    return data


def post_json(url, payload, key, timeout):
    """POST JSON，返回解析后的 dict。429 抛 RateLimitError，其它 HTTP 错误抛带 status 的 RuntimeError。"""
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
    if key: req.add_header('Authorization', 'Bearer ' + key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            ra = e.headers.get('Retry-After') if e.headers else None
            try:
                ra = int(ra) if ra else None
            except ValueError:
                ra = None
            raise RateLimitError(ra)
        err_body = ''
        try:
            err_body = e.read().decode('utf-8', errors='replace')[:300]
        except Exception:
            pass
        err = RuntimeError(f"HTTP {e.code}: {err_body}")
        err.status = e.code
        raise err




def remote_analyze(images, prompt, result_only=False, skip_downscale=False, skip_normalize=False):
    """调用远端 VLM：降采样发送 + 429 退避重试 + JSON 自动修复 + 可选 normalize。"""
    base, model, key = remote_env_state()
    content = [{'type': 'text', 'text': prompt}]
    orig_dims = []
    for image in images:
        validate_image_file(image)
        if skip_downscale:
            mime = mimetypes.guess_type(image)[0] or 'image/jpeg'
            from PIL import Image, ImageOps
            im = ImageOps.exif_transpose(Image.open(image))
            orig_dims.append(im.size)
            raw = Path(image).read_bytes()
        else:
            mime, raw, ow, oh = downscale_image(image)
            orig_dims.append((ow, oh))
        b64 = base64.b64encode(raw).decode('ascii')
        content.append({'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}})
    payload = {'model': model, 'messages': [{'role': 'user', 'content': content}], 'max_tokens': 8192}
    retries, timeout, last = 2, 120.0, None
    for attempt in range(retries + 1):
        try:
            raw_resp = post_json(base + '/chat/completions', payload, key, timeout)
            text = raw_resp['choices'][0]['message']['content']
            parsed = extract_json_text(text)
            if result_only:
                if parsed is None: raise RuntimeError('model response is not valid JSON')
                if not skip_normalize:
                    ow, oh = orig_dims[0] if orig_dims else (None, None)
                    parsed = normalize_result(parsed, width=ow, height=oh)
                return parsed
            return {'provider': 'remote', 'model': model, 'content': text,
                    'parsed_json': parsed, 'raw_response': raw_resp}
        except RateLimitError as e:
            last = e
            if attempt < retries:
                wait = e.retry_after if e.retry_after else min(5 * (2 ** attempt), 60)
                wait = min(wait, 60)
                print(f"[visual_runtime] 429 限流，{wait}s 后重试（{attempt + 1}/{retries}）", file=sys.stderr)
                time.sleep(wait)
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(min(2 ** attempt, 2))
    raise RuntimeError(str(last))


def main():
    p = argparse.ArgumentParser(description='远端 VLM 图片分析（VISUAL_BASE_URL/VISUAL_MODEL/VISUAL_API_KEY）')
    p.add_argument('--config', help=argparse.SUPPRESS)  # 兼容旧调用：静默忽略
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('remote-analyze', help='把图片发给远端 VLM 分析')
    a.add_argument('images', nargs='+')
    a.add_argument('--prompt')
    a.add_argument('--prompt-file')
    a.add_argument('--result-only', action='store_true')
    a.add_argument('--max-image-bytes', type=int, default=DEFAULT_MAX_IMAGE_BYTES)
    a.add_argument('--no-downscale', action='store_true', help='禁用降采样（大图/稠密图精确读取时用）')
    a.add_argument('--no-normalize', action='store_true', help='禁用输出 normalize')
    args = p.parse_args()
    prompt = args.prompt
    if args.prompt_file: prompt = Path(args.prompt_file).read_text(encoding='utf-8')
    if not prompt: raise SystemExit('--prompt or --prompt-file is required')
    result = remote_analyze(args.images, prompt, args.result_only,
                            skip_downscale=args.no_downscale, skip_normalize=args.no_normalize)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main() or 0)
