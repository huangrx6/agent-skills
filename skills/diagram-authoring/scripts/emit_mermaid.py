#!/usr/bin/env python3
"""Structure spec → editable .mmd; no browser, images or sidecar reports."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile


def load(name):
    key = '_mermaid_' + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


def ident(value, prefix='n'):
    # Independent of declaration order, Unicode, punctuation and reserved words.
    return prefix + hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def label(value):
    """Quoted Mermaid text; entity-encode syntax/HTML characters, keep line breaks."""
    return ''.join('<br/>' if c == '\n' else f'#{ord(c)};' if c in '#"<>|{}[]`\\&:;%' else c
                   for c in value.replace('\r\n', '\n').replace('\r', '\n'))


def emit(spec, *, colors=None):
    report = load('validate_spec').validate(spec)
    if report.errors:
        raise ValueError('规格不通过：' + '; '.join(str(e) for e in report.errors))
    kind = spec['type']
    if kind not in ('architecture', 'dependency', 'flow', 'state'):
        raise ValueError('Mermaid 生成器目前支持 architecture/dependency/flow/state；不把径向或力导向图静默改成流程图')
    for node in spec['nodes']:
        if any(key in node for key in ('icon', 'rank', 'pin')):
            raise ValueError(f"节点 {node['id']}：Mermaid 不支持本契约的 icon/rank/pin；请改用其他后端或明确调整规格")
    state = kind == 'state'
    if state and (spec.get('groups') or spec.get('cards') or
                  any(n.get('shape') not in (None, 'rect', 'round') for n in spec['nodes']) or
                  any(e.get('kind', 'sync') != 'sync' for e in spec.get('edges', []))):
        raise ValueError('stateDiagram-v2 当前仅支持普通状态与同步转移；分组、卡片、特殊形状和非同步边请用其他后端，不能丢弃')
    palette = load('palette')
    palette.use_backend('drawio', mood=spec.get('mood'), visual=spec.get('visual'))
    if colors is not None:
        palette.use_colors(colors, spec=spec)
    layout = load('layout')
    detail = spec.get('detail', 'standard')
    config = {'theme': 'base', 'securityLevel': 'strict',
              'themeVariables': {'background': palette.CANVAS['background'],
                                'primaryTextColor': palette.CANVAS['text'],
                                'edgeLabelBackground': palette.CANVAS['background'],
                                'lineColor': palette.ROLES['edge'], 'fontSize': '18px'},
              'markdownAutoWrap': False,
              'themeCSS': '.diagram_note .label { text-align:left !important; } '
                          '.diagram_note text { text-anchor:start !important; '
                          'transform:translateX(-50%); transform-box:fill-box; }',
              'flowchart': {'nodeSpacing': 56, 'rankSpacing': 100, 'curve': 'linear',
                            'wrappingWidth': 800,
                            'diagramPadding': 16, 'subGraphTitleMargin': {'top': 16, 'bottom': 24}},
              'state': {'padding': 24, 'nodeSpacing': 56, 'rankSpacing': 100}}
    lines = ['---']
    if spec.get('title'):
        lines.append('title: ' + json.dumps(spec['title'], ensure_ascii=False))
    lines += ['config: ' + json.dumps(config, ensure_ascii=False), '---']
    direction = spec.get('direction', 'LR' if kind in ('architecture', 'state') else 'TB')
    cards = spec.get('cards', [])
    lines += ['stateDiagram-v2', '  direction ' + direction] if state else ['flowchart ' + ('TB' if cards else direction)]
    if cards:
        # Link containers, not business nodes. This is a layout constraint only.
        lines += ['  subgraph diagram_main[" "]', '    direction ' + direction]
    styles = []
    metrics = load('text_metrics')

    def wrapped(text, units):
        return '\n'.join(metrics.wrap(text, units)[0])
    shapes = {'rect': ('["', '"]'), 'round': ('("', '")'),
              'capsule': ('(["', '"])'), 'ellipse': ('(["', '"])'),
              'diamond': ('{"', '"}'), 'cylinder': ('[("', '")]'), 'note': ('["', '"]')}

    def node_line(node):
        nid = ident(node['id'])
        text = wrapped(node['label'], 22)
        if node.get('detail') and layout.shows_node_detail(node, detail):
            text += '\n' + wrapped(node['detail'], 28)
        role, emphasis = node['kind'], node.get('emphasis', 'normal')
        style = (f'fill:{palette.fill_for(role, emphasis, node["id"])},'
                 f'stroke:{palette.stroke_for(role, emphasis, node["id"])},'
                 f'color:{palette.text_for(role, emphasis, node["id"])},'
                 f'stroke-width:{2 if emphasis in ("primary", "critical") else 1}px')
        shape = load('shapes').resolve(node)
        if shape == 'note' and not state:
            style += ',stroke-dasharray:4 3'
        styles.extend([f'  classDef c{nid} {style}', f'  class {nid} c{nid}'])
        if state:
            return f'  state "{label(text)}" as {nid}'
        left, right = shapes[shape]
        return f'  {nid}{left}{label(text)}{right}'

    for node in spec['nodes']:
        if not node.get('group'):
            lines.append(node_line(node))
    for group in spec.get('groups', []):
        gid = ident(group['id'], 'g')
        title = group.get('label', group['id'])
        if group.get('description'):
            title += '\n' + group['description']
        lines.append(f'  subgraph {gid}["{label(title)}"]')
        lines.extend('  ' + node_line(n) for n in spec['nodes'] if n.get('group') == group['id'])
        lines.append('  end')
        color = palette.group_colors(group['id'], group.get('level', 'tint'))
        styles.append(f'  style {gid} fill:{color["fill"]},stroke:{color["stroke"]},color:{color["text"]}')
    for edge in spec.get('edges', []):
        source, target = ident(edge['from']), ident(edge['to'])
        text = edge.get('label', '') if layout.shows_edge_label(edge, detail) else ''
        if not text and detail == 'diagnostic' and edge.get('kind', 'sync') != 'sync':
            text = palette.EDGE_KINDS[edge['kind']]['zh']
        if state:
            lines.append(f'  {source} --> {target}' + (f' : {label(text)}' if text else ''))
        else:
            arrow = '-.->' if edge.get('kind') in ('async', 'optional') else '-->'
            lines.append(f'  {source} {arrow}' + (f'|"{label(text)}"|' if text else '') + f' {target}')
    if cards:
        lines += ['  end', '  subgraph diagram_notes[" "]', '    direction LR']
    for index, card in enumerate(cards):
        # Body paragraphs read horizontally; blank lines separate complete items.
        # A zero-width spacer keeps paragraph breaks in native SVG labels too;
        # Mermaid drops empty <br/> lines in that rendering mode.
        paragraph = '\n\u200b\n'
        text = wrapped(card['title'], 36) + paragraph + paragraph.join(
            wrapped('• ' + item, 40) for item in card['items'])
        lines.append(f'  card{index}["{label(text)}"]')
        lines.append(f'  class card{index} diagram_note')
        styles.append(f'  style card{index} fill:{palette.CANVAS["background"]},stroke:{palette.ROLES["edge"]},stroke-dasharray:4 3,color:{palette.CANVAS["text"]},text-align:left')
    if cards:
        lines += ['  end', '  %% Layout-only invisible link: no business relationship.',
                  '  diagram_main ~~~ diagram_notes']
        styles += ['  style diagram_main fill:transparent,stroke:transparent',
                   '  style diagram_notes fill:transparent,stroke:transparent']
    return '\n'.join(lines + styles) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('-o', '--out', type=Path)
    parser.add_argument('--colors')
    parser.add_argument('--stdout', action='store_true')
    args = parser.parse_args(argv)
    try:
        text = emit(json.loads(args.spec.read_text(encoding='utf-8')), colors=args.colors)
        if args.stdout:
            print(text, end='')
            return 0
        out = args.out or Path(load('output_paths').default_output(str(args.spec), '.mmd'))
        if out.resolve() in {args.spec.resolve(), Path(args.colors).resolve() if args.colors else args.spec.resolve()}:
            raise ValueError('输出不能覆盖规格或配色输入')
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=out.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(text)
        try:
            os.replace(temp, out)
        finally:
            temp.unlink(missing_ok=True)
        print(f'已生成 {out}；结构规格通过，Mermaid 官方语法与真实布局尚未验证。')
        print('请运行 check_mermaid.py，再运行 sync_exports.py；没有已有图片时不会导出。')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
