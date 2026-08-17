#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0.0"]
# ///
"""快速看图：把本地图片发给 OpenAI-compatible 视觉模型，直接返回 Markdown 描述。

环境变量（三个都必需，通常写在 ~/.zshrc，改后需重启终端/DSH 宿主）：
  VISUAL_BASE_URL  如 https://open.bigmodel.cn/api/paas/v4
  VISUAL_MODEL     如 glm-4.6v-flash
  VISUAL_API_KEY   服务商 API Key

用法（uv run 自动装依赖）：
  uv run scripts/visual_runtime.py <图片...>                    # 快速看图 → Markdown
  uv run scripts/visual_runtime.py img.png --no-downscale       # 稠密小字/大图，保原分辨率
  uv run scripts/visual_runtime.py img.png --prompt "图里报错怎么解"   # 针对性提问
  uv run scripts/visual_runtime.py img.png --json               # 输出严格 JSON（自定义 prompt 用）
"""
from __future__ import annotations
import argparse, base64, io, json, mimetypes, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

ENV_VARS = ('VISUAL_BASE_URL', 'VISUAL_MODEL', 'VISUAL_API_KEY')
DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024
SUPPORTED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
QUICK_LOOK_PROMPT = str(Path(__file__).resolve().parent.parent / 'assets' / 'prompts' / 'quick-look.md')


class RateLimitError(Exception):
    """429 限流，可携带 Retry-After 秒数。"""

    def __init__(self, retry_after=None):
        # retry_after 是服务端 Retry-After 头解析出的秒数（int），也可能是 None
        super().__init__(
            f"rate limited (Retry-After={retry_after}s)"
            if retry_after is not None
            else "rate limited"
        )
        self.retry_after = retry_after


def load_endpoint():
    """读三个环境变量；缺失时给出可直接照做的配置指引并退出。"""
    missing = [v for v in ENV_VARS if not os.getenv(v, '').strip()]
    if missing:
        print('缺少视觉模型环境变量: ' + ', '.join(missing), file=sys.stderr)
        print('请在 ~/.zshrc（或对应 shell 配置）中添加并重启终端/DSH 宿主：', file=sys.stderr)
        print('  export VISUAL_BASE_URL=https://open.bigmodel.cn/api/paas/v4', file=sys.stderr)
        print('  export VISUAL_MODEL=glm-4.6v-flash', file=sys.stderr)
        print('  export VISUAL_API_KEY=<你的Key>', file=sys.stderr)
        raise SystemExit(2)
    return os.getenv('VISUAL_BASE_URL').rstrip('/'), os.getenv('VISUAL_MODEL'), os.getenv('VISUAL_API_KEY')


def validate_image_file(path, max_bytes=DEFAULT_MAX_IMAGE_BYTES):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"图片文件不存在: {p}")
    size = p.stat().st_size
    if size == 0:
        raise SystemExit(f"图片文件为空: {p}")
    if size > max_bytes:
        raise SystemExit(f"图片文件过大: {p} ({size} bytes > {max_bytes} bytes)")
    mime = mimetypes.guess_type(p.name)[0] or ''
    if mime.lower() not in SUPPORTED_IMAGE_MIMES:
        raise SystemExit(f"图片类型不支持: {mime or '未知'}（{p}）；支持 {sorted(SUPPORTED_IMAGE_MIMES)}")
    return mime.lower()


def downscale_image(path, max_dim=1568, quality=85):
    """降采样大图 + JPEG 压缩，减少上行 token 与延迟。返回 (mime, bytes)。"""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path))
    orig_w, orig_h = im.size
    if max(orig_w, orig_h) <= max_dim and Path(path).suffix.lower() in ('.jpg', '.jpeg'):
        return 'image/jpeg', Path(path).read_bytes()
    im = im.convert('RGB')
    if max(orig_w, orig_h) > max_dim:
        ratio = max_dim / max(orig_w, orig_h)
        im = im.resize((round(orig_w * ratio), round(orig_h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=quality)
    return 'image/jpeg', buf.getvalue()


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


def post_json(url, payload, key, timeout):
    """POST JSON。429 抛 RateLimitError，其它 HTTP 错误抛带 status 的 RuntimeError。"""
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
        raise RuntimeError(f"HTTP {e.code}: {err_body}")


def analyze(images, prompt, no_downscale=False, as_json=False, max_tokens=8192, timeout=120.0, max_retries=2):
    base, model, key = load_endpoint()
    content = [{'type': 'text', 'text': prompt}]
    for image in images:
        validate_image_file(image)
        if no_downscale:
            mime = mimetypes.guess_type(image)[0] or 'image/jpeg'
            raw = Path(image).read_bytes()
        else:
            mime, raw = downscale_image(image)
        b64 = base64.b64encode(raw).decode('ascii')
        content.append({'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}})
    payload = {'model': model, 'messages': [{'role': 'user', 'content': content}], 'max_tokens': max_tokens}
    last = None
    for attempt in range(max_retries + 1):
        try:
            raw_resp = post_json(base + '/chat/completions', payload, key, timeout)
            text = raw_resp['choices'][0]['message']['content']
            if as_json:
                parsed = extract_json_text(text)
                if parsed is None:
                    raise RuntimeError('模型未返回合法 JSON（已尝试自动修复）；请简化 prompt 或去掉 --json')
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            return text
        except RateLimitError as e:
            last = e
            if attempt < max_retries:
                wait = e.retry_after if e.retry_after else min(5 * (2 ** attempt), 60)
                print(f"[visual] 429 限流，{wait}s 后重试（{attempt + 1}/{max_retries}）", file=sys.stderr)
                time.sleep(wait)
        except Exception as e:
            last = e
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 2))
    raise RuntimeError(str(last))


def main():
    p = argparse.ArgumentParser(description='快速看图：图片 → 远端视觉模型 → Markdown/JSON')
    p.add_argument('images', nargs='+')
    p.add_argument('--prompt', help='自定义提问（默认用 assets/prompts/quick-look.md 整体看图）')
    p.add_argument('--prompt-file')
    p.add_argument('--no-downscale', action='store_true', help='禁用降采样（稠密小字/大图精确读取）')
    p.add_argument('--json', action='store_true', help='输出严格 JSON（配合自定义 --prompt 使用）')
    args = p.parse_args()
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding='utf-8')
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = Path(QUICK_LOOK_PROMPT).read_text(encoding='utf-8')
    print(analyze(args.images, prompt, no_downscale=args.no_downscale, as_json=args.json))
    return 0


if __name__ == '__main__':
    raise SystemExit(main() or 0)
