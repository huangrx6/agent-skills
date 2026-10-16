#!/usr/bin/env python3
"""Inspect an official SVG in a real browser against its editable source.

Supported: this skill's Excalidraw utils 0.1.5 / draw.io SVG exports, one page.
Checks visible label inventory, arrow path inventory, canvas clipping, declared
font availability, viewing font size, rectangular overflow clips, text box overlap
and likely occlusion by later opaque SVG shapes. Does not prove correct topology,
glyph fallback, arbitrary masks/clips, or PNG equality. No network requests.
0=checked with no findings; 1=findings; 2=skipped/unmeasurable/invalid input.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
from html import unescape
from html.parser import HTMLParser
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parent
EXPORT = load(HERE / 'export_excalidraw.py', '_render_export')
A = load(HERE.parent / 'scripts/authoring.py', '_render_authoring')
LIMITS = ['未识别每个汉字的实际回退字体或缺字方框',
          '内部裁切仅检查矩形 overflow；不检查任意 clipPath/mask 或形状内文字安全区',
          '重叠按文字包围盒，遮挡按后绘制不透明 SVG 填充采样；不覆盖图像、滤镜、透明叠层或所有字形像素',
          '未证明箭头语义方向正确',
          '只检查指定 SVG；不证明同名 PNG 或其他页一致', '箭头检查适配本工具的官方导出结构，未支持任意外部 SVG']


def norm(text):
    return re.sub(r'\s+', '', text)


class LabelText(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.parts = []; self.feed(text)
    def handle_data(self, data):
        self.parts.append(data)


def expected(path):
    source = path.read_text(encoding='utf-8')
    if path.suffix == '.excalidraw':
        scene = json.loads(source)
        if scene.get('type') != 'excalidraw': raise ValueError('需要 Excalidraw 场景')
        elements = [e for e in scene['elements'] if not e.get('isDeleted')]
        if any(e.get('type') == 'image' or e.get('id', '').startswith('icon-') for e in elements):
            raise ValueError('含图标/图片的 Excalidraw 暂不支持箭头清点；请目视审查')
        return {'backend':'excalidraw', 'labels': [norm(line) for e in elements if e.get('type')=='text'
                  for line in e['text'].splitlines() if norm(line)],
                'arrows':len([e for e in elements if e.get('type')=='arrow']), 'cells':{}}
    if path.suffix == '.drawio':
        root = load(HERE.parent / 'scripts/drawio_xml.py', '_render_drawio_xml').parse(source)
        if len(root.findall('diagram')) != 1:
            raise ValueError('目前只检查本工具的单页 draw.io；多页请逐页导出并提供对应单页源文件')
        cells = {}; edges=[]
        for cell in root.iter('mxCell'):
            ident=cell.get('id','')
            if cell.get('edge')=='1':edges.append(ident)
            if cell.get('value') and (cell.get('vertex')=='1' or cell.get('edge')=='1'):
                cells[ident]=norm(''.join(LabelText(cell.get('value')).parts))
        for obj in [*root.iter('UserObject'), *root.iter('object')]:
            cells[obj.get('id')]=norm(''.join(LabelText(obj.get('label','')).parts))
        return {'backend':'drawio','labels':[], 'cells':cells,'edges':edges}
    raise ValueError('需要 .excalidraw 或 .drawio 源文件')


def safe_svg(source):
    # draw.io emits the standard external SVG DTD. Remove that declaration;
    # never resolve it, and reject internal subsets or entity declarations.
    source=re.sub(r'<!DOCTYPE\s+svg\s+(?:PUBLIC|SYSTEM)\s+[^<>\[\]]+>', '', source, flags=re.I)
    if '<!DOCTYPE' in source.upper() or '<!ENTITY' in source.upper():
        raise ValueError('不检查包含 XML 实体的 SVG')
    root=ET.fromstring(source)
    if root.tag.rsplit('}',1)[-1] != 'svg': raise ValueError('需要 SVG 根元素')
    for el in root.iter():
        tag=el.tag.rsplit('}',1)[-1]
        if tag in ('script','iframe','object','embed','audio','video','animate','set','animateTransform','animateMotion'):
            raise ValueError('SVG 包含不支持的主动内容')
        for key,value in el.attrib.items():
            key=key.rsplit('}',1)[-1].lower()
            if key.startswith('on'): raise ValueError('SVG 含事件处理器')
            if tag == 'a' and key == 'href' and value.startswith(('https://','http://')):
                continue  # Inert documentation link; the probe never navigates.
            if key in ('href','src') and not value.startswith(('#','data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
                raise ValueError('SVG 含外部或不支持的资源链接')
    return source


def probe(source, browser):
    # CSP blocks external fonts/images/styles even if the SVG contains CSS URLs.
    encoded=base64.b64encode(source.encode()).decode()
    js=(HERE/'render_probe.js').read_text()
    page=('''<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:">
<style>body{margin:0}#result{display:none}</style><pre id="result" data-status="running"></pre>'''
          +'<script id="svg-data" type="application/octet-stream">'+encoded+'</script><script>'+js+'</script>')
    with tempfile.TemporaryDirectory(prefix='diagram-render-check-') as td:
        path=Path(td)/'check.html';path.write_text(page)
        dom=EXPORT._dump_dom(browser,str(path))
    found=re.search(r'<pre id="result"[^>]*data-status="(ok|error)"[^>]*>(.*?)</pre>',dom,re.S)
    if not found: raise ValueError('浏览器未返回检查结果')
    result=json.loads(unescape(found.group(2)))
    if found.group(1)!='ok': raise ValueError(result.get('error','浏览器检查失败'))
    return result


def assess(want, observed, preset='fit', width=None, height=None):
    findings=[]
    def add(code,message,**evidence):findings.append({'code':'render/'+code,'message':message,'evidence':evidence})
    canvas=observed['canvas'];cw,ch=canvas['width'],canvas['height']
    if not all(math.isfinite(x) and x>0 for x in (cw,ch)):raise ValueError('SVG 画布不可测量')
    for axis,target in (('width',width),('height',height)):
        if target is not None and abs(canvas[axis]-target)>1:
            add('size','实际 SVG 画布与指定尺寸不符',axis=axis,actual=canvas[axis],expected=target)
    def outside(box):
        return (box['x']<canvas['x']-1.5 or box['y']<canvas['y']-1.5
                or box['x']+box['width']>canvas['x']+cw+1.5
                or box['y']+box['height']>canvas['y']+ch+1.5)
    clipped=[t['text'] for t in observed['texts'] if outside(t['box'])]
    graphics=sum(outside(g['box']) for g in observed['graphics'])
    if clipped or graphics:add('canvas-clipping','实际文字或图形超出 SVG 画布',labels=clipped,graphics=graphics)
    if observed.get('clipped'):
        add('internal-clipping','文字超出实际矩形裁切区域',labels=observed['clipped'])
    if observed.get('overlaps'):
        add('text-overlap','实际文字包围盒明显重叠，需目视核对',pairs=observed['overlaps'])
    if observed.get('occluded'):
        add('text-occluded','文字可能被后绘制的不透明图形遮挡',labels=observed['occluded'])
    # Visible source text must actually occur in exported DOM, preserving multiplicity.
    if want['backend']=='excalidraw':
        missing=Counter(want['labels'])-Counter(norm(t['text']) for t in observed['texts'])
        if missing:add('label-missing','导出缺少可见文字',labels=dict(missing))
        arrows=observed['arrows']
        if len(arrows)!=want['arrows'] or any(n<3 for n in arrows):
            add('arrow-inventory','导出箭头或箭头头部路径不完整',expected=want['arrows'],path_counts=arrows)
    else:
        actual={}
        for t in observed['texts']:
            if t.get('cell'):actual[t['cell']]=actual.get(t['cell'],'')+norm(t['text'])
        missing={key:label for key,label in want['cells'].items() if label and actual.get(key)!=label}
        if missing:add('label-missing','导出单元格文字缺失或不一致',cells=missing)
        paths={c['id']:c['paths'] for c in observed['cells']}
        missing_edges=[key for key in want['edges'] if paths.get(key,0)<2]
        if missing_edges:add('arrow-inventory','导出连线或箭头头部路径缺失',cells=missing_edges)
    unavailable=[f['family'] for f in observed['fonts'] if not f['available']]
    if unavailable or observed['failed_faces']:
        add('font-unavailable','声明字体不可用或加载失败，存在字体替换',families=unavailable,failed_faces=observed['failed_faces'])
    target=A.PRESETS[preset]
    scale=min([1.0]+[target[axis]/canvas[axis] for axis in ('width','height') if target[axis]])
    small=[{'text':t['text'],'px':round(t['px']*scale,2)} for t in observed['texts']
           if target['min_text'] and t['px']*scale<target['min_text']-0.1]
    if small:add('small-text','真实 SVG 在指定观看场景下的文字过小',labels=small,preset=preset)
    if not observed['texts']:add('no-text','没有测到可见文字')
    if observed['font_status']!='loaded':add('font-pending','字体尚未完成加载')
    return {'status':'failed' if findings else 'pass','basis':'browser-rendered-official-svg',
            'preset':preset,'findings':findings,'limits':LIMITS,
            'measurements':{'canvas':canvas,'texts':len(observed['texts']),
                            'min_viewing_px':round(min((t['px'] for t in observed['texts']),default=0)*scale,2),
                            'fonts':observed['fonts']}}


def inspect(artifact, svg, *, browser=None, preset='fit', width=None, height=None):
    try:
        want=expected(Path(artifact));source=safe_svg(Path(svg).read_text())
        exe=EXPORT.find_browser(browser)
        if not exe:return {'status':'skipped','reason':'找不到浏览器，未执行真实渲染检查','limits':LIMITS}
        measured=probe(source,exe)
        result=assess(want,measured,preset,width,height)
        import hashlib
        result['source_sha256']=hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        result['svg_sha256']=hashlib.sha256(Path(svg).read_bytes()).hexdigest()
        return result
    except (OSError,ValueError,TypeError,KeyError,AttributeError,IndexError,ET.ParseError,RuntimeError,subprocess.TimeoutExpired) as exc:
        return {'status':'unmeasurable','reason':str(exc),'limits':LIMITS}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('artifact');p.add_argument('svg');p.add_argument('--browser')
    p.add_argument('--preset',choices=A.PRESETS,default='fit')
    p.add_argument('--width',type=int);p.add_argument('--height',type=int)
    p.add_argument('--json',action='store_true');args=p.parse_args(argv)
    result=inspect(args.artifact,args.svg,browser=args.browser,preset=args.preset,width=args.width,height=args.height)
    print(json.dumps(result,ensure_ascii=False,indent=2) if args.json else result)
    return 0 if result['status']=='pass' else 1 if result['status']=='failed' else 2


if __name__=='__main__':sys.exit(main())
