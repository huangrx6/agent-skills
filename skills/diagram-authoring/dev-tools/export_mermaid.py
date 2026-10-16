#!/usr/bin/env python3
"""Official Mermaid parser/renderer in a local browser; images only on request.

Loads a pinned official Mermaid ESM bundle from jsDelivr, like the Excalidraw
exporter. The diagram is processed in the browser, not posted to a rendering API.
Syntax-only mode calls parse(), not render(), and creates no image files.
"""
from __future__ import annotations
import argparse
import base64
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

VERSION = '11.12.0'
CDN = f'https://cdn.jsdelivr.net/npm/mermaid@{VERSION}/dist/mermaid.esm.min.mjs'
DEFAULT_PADDING = 80
FORMATS = ('png', 'svg')

PAGE = r'''<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; connect-src https://cdn.jsdelivr.net; style-src 'unsafe-inline'; img-src data: blob:; font-src data:;">
<pre id="result"></pre><script type="module">
const args = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('__ARGS__'), c=>c.charCodeAt(0))));
const result = document.querySelector('#result');
function finish(data) {
  const bytes = new TextEncoder().encode(JSON.stringify(data));
  let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
  result.textContent = btoa(binary);
}
try {
  const {default: mermaid} = await import('__CDN__');
  mermaid.initialize({startOnLoad:false, securityLevel:'strict', htmlLabels:false, flowchart:{htmlLabels:false},
    secure:['securityLevel','htmlLabels','startOnLoad','secure']});
  const parsed = await mermaid.parse(args.source);
  if (!args.format) {
    finish({ok:true, stage:'syntax', diagramType:parsed.diagramType, rendered:false});
  } else {
    await document.fonts.ready;
    const {svg} = await mermaid.render('mermaid-diagram', args.source);
    // Mermaid returns browser markup (HTML entities may occur in labels).
    const doc = document.implementation.createHTMLDocument('');
    doc.body.innerHTML = svg;
    const root = doc.querySelector('svg');
    if (!root) throw Error('Mermaid 没有返回 SVG');
    // Mermaid 11.12 text labels can leave one HTML-encoding layer inside SVG
    // text nodes. Decode exactly once as TEXT, never insert decoded markup.
    // The .mmd keeps the host's HTML label default; only this raster-safe export
    // requests native SVG labels. Literal '&lt;' remains literal after one pass.
    const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (!node.parentElement.closest('text')) continue;
      const decoder = document.createElement('textarea');
      decoder.innerHTML = node.nodeValue;
      node.nodeValue = decoder.value;
    }
    const box = root.getAttribute('viewBox').split(/[ ,]+/).map(Number);
    if (box.length !== 4 || !box.every(Number.isFinite) || box[2] <= 0 || box[3] <= 0) throw Error('无效的 SVG 内容边界');
    const [x,y,w,h] = box, p = args.padding;
    const width = w+2*p, height = h+2*p;
    if (width*height*args.scale*args.scale > 100000000) throw Error('图片尺寸超过 1 亿像素，请降低倍率或拆分视图');
    root.setAttribute('viewBox', `${x-p} ${y-p} ${width} ${height}`);
    root.setAttribute('width', String(width)); root.setAttribute('height', String(height));
    root.style.maxWidth = 'none';
    const config = mermaid.mermaidAPI.getConfig();
    const bg = config.themeVariables?.background || '#ffffff';
    const rect = doc.createElementNS('http://www.w3.org/2000/svg','rect');
    for (const [k,v] of Object.entries({x:x-p,y:y-p,width,height,fill:bg})) rect.setAttribute(k,String(v));
    root.insertBefore(rect,root.firstChild);
    const serialized = new XMLSerializer().serializeToString(root);
    if (args.format === 'svg') finish({ok:true, stage:'render', svg:serialized, width, height});
    else {
      if (root.querySelector('foreignObject')) throw Error('PNG 导出需要原生 SVG 标签；请将 htmlLabels 与 flowchart.htmlLabels 设为 false，或只导出 SVG');
      const blob = new Blob([serialized], {type:'image/svg+xml;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const img = new Image();
      await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('SVG 光栅化失败'));img.src=url;});
      const canvas = document.createElement('canvas');
      canvas.width=Math.ceil(width*args.scale); canvas.height=Math.ceil(height*args.scale);
      canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);
      const png=canvas.toDataURL('image/png').split(',')[1]; URL.revokeObjectURL(url);
      finish({ok:true, stage:'render', png, width:canvas.width, height:canvas.height});
    }
  }
} catch (e) { finish({ok:false, stage:'mermaid', message:String(e)}); }
</script>'''


def browser_tools():
    spec = importlib.util.spec_from_file_location('_mermaid_browser', Path(__file__).with_name('export_excalidraw.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(source, *, fmt=None, scale=2.0, padding=DEFAULT_PADDING, browser=None):
    try:
        if fmt is not None and fmt not in FORMATS:
            raise ValueError('Mermaid 当前只导出 PNG/SVG')
        scale, padding = float(scale), float(padding)
        if not math.isfinite(scale) or scale <= 0 or not math.isfinite(padding) or padding < 0:
            raise ValueError('scale 必须为有限正数；padding 必须为有限非负数')
        text = Path(source).read_text(encoding='utf-8')
        if not text.strip():
            raise ValueError('Mermaid 源文件为空')
        engine = browser_tools()
        exe = engine.find_browser(browser or os.environ.get('MERMAID_EXPORT_BROWSER'))
        if not exe:
            return {'ok':False, 'stage':'environment', 'message':'找不到 Chrome/Chromium；用 --browser 或 MERMAID_EXPORT_BROWSER 指定。源文件仍可交付，不能宣称语法/渲染已验证。'}
        payload = base64.b64encode(json.dumps({'source':text, 'format':fmt, 'scale':scale, 'padding':padding}).encode()).decode()
        page = PAGE.replace('__ARGS__', payload).replace('__CDN__', CDN)
        with tempfile.TemporaryDirectory(prefix='mermaid-') as td:
            html = Path(td) / 'render.html'
            html.write_text(page, encoding='utf-8')
            dom = engine._dump_dom(exe, str(html))
        match = re.search(r'<pre id="result">([A-Za-z0-9+/=]+)</pre>', dom)
        if not match:
            raise RuntimeError('官方 Mermaid 未返回结果；检查浏览器或 CDN 网络连接，未验证不能算通过')
        result = json.loads(base64.b64decode(match[1]).decode('utf-8'))
        result['engine'] = 'Mermaid ' + VERSION
        return result
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return {'ok':False, 'stage':'runtime', 'message':str(exc)}


def export(source, out, fmt='png', scale=2.0, padding=DEFAULT_PADDING, browser=None):
    if Path(source).resolve() == Path(out).resolve():
        return {'ok':False, 'stage':'input', 'message':'导出不能覆盖 Mermaid 源文件'}
    result = run(source, fmt=fmt, scale=scale, padding=padding, browser=browser)
    if not result['ok']:
        return result
    try:
        data = result.pop('svg').encode('utf-8') if fmt == 'svg' else base64.b64decode(result.pop('png'))
        target = Path(out)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(data)
        try:
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return {**result, 'out':str(target.absolute()), 'format':fmt}
    except (OSError, ValueError, KeyError) as exc:
        return {'ok':False, 'stage':'output', 'message':str(exc)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('-o', '--out', required=True)
    parser.add_argument('--format', choices=FORMATS)
    parser.add_argument('--scale', type=float, default=2)
    parser.add_argument('--padding', type=float, default=DEFAULT_PADDING)
    parser.add_argument('--browser')
    args = parser.parse_args(argv)
    result = export(args.source, args.out, args.format or Path(args.out).suffix[1:], args.scale, args.padding, args.browser)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
