#!/usr/bin/env python3
"""Run small synthetic SVG controls through the real browser probe.

These fixtures calibrate detection, not the official diagram exporters. Do not
use the result as a substitute for checking a user's actual exported diagram.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('probe_regression', HERE / 'check_render.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def cases():
    prefix = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200"><rect width="400" height="200" fill="white"/>'
    label = '<text x="40" y="70" font-family="Helvetica" font-size="24">Base label</text>'
    second = '<text x="40" y="140" font-family="Helvetica" font-size="24">Second label</text>'
    cover = '<rect x="30" y="40" width="220" height="50" fill="#333333"/>'
    def scene(body): return prefix + body + '</svg>'
    want = {'backend':'excalidraw','labels':['Baselabel','Secondlabel'],'arrows':0,'cells':{}}
    tests = [
        ('separate-labels', scene(label+second), want, set()),
        ('overlapping-labels', scene(label+second.replace('y="140"','y="70"')), want, {'render/text-overlap'}),
        ('opaque-cover', scene(label+second+cover), want, {'render/text-occluded'}),
        ('transparent-cover', scene(label+second+cover.replace('fill=', 'opacity="0.1" fill=')), want, set()),
        ('cover-behind-text', scene(cover+label+second), want, set()),
    ]
    for overflow in ('hidden', 'visible'):
        body = ('<foreignObject x="40" y="40" width="20" height="50" style="overflow:visible">'
                '<div xmlns="http://www.w3.org/1999/xhtml" style="width:20px;white-space:nowrap;'
                f'overflow:{overflow};font:24px Helvetica">Clipped label</div></foreignObject>')
        w = {'backend':'excalidraw','labels':['Clippedlabel'],'arrows':0,'cells':{}}
        tests.append(('overflow-'+overflow, scene(body), w,
                      {'render/internal-clipping'} if overflow=='hidden' else set()))
    return tests


def run(browser=None):
    exe=R.EXPORT.find_browser(browser)
    if not exe:
        return {'status':'skipped','reason':'找不到浏览器；未执行实际 SVG 控制实验'}
    results=[]
    for name, svg, want, expected in cases():
        observed=R.probe(R.safe_svg(svg),exe)
        report=R.assess(want,observed)
        codes={f['code'] for f in report['findings']}
        results.append({'case':name,'expected':sorted(expected),'actual':sorted(codes),'pass':codes==expected})
    return {'status':'pass' if all(r['pass'] for r in results) else 'failed',
            'basis':'real-browser-synthetic-svg-controls','cases':results,
            'limits':['合成 SVG 控制实验；不代表任意图形、字体或真实业务图均已通过']}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--browser');p.add_argument('-o','--out',type=Path)
    args=p.parse_args(argv)
    try:
        report=run(args.browser)
    except (OSError,ValueError,RuntimeError) as error:
        report={'status':'unmeasurable','reason':str(error)}
    payload=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.out:args.out.write_text(payload,encoding='utf-8')
    else:print(payload,end='')
    return 0 if report['status']=='pass' else 1 if report['status']=='failed' else 2


if __name__=='__main__':sys.exit(main())
