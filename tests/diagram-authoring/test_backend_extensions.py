"""Backend boundaries, compressed editor roundtrips and export ownership."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

BASE = Path(__file__).resolve().parents[2] / 'skills/diagram-authoring'

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, BASE / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

M = load('test_mermaid_emit', 'scripts/emit_mermaid.py')
R = load('test_mermaid_runtime', 'dev-tools/export_mermaid.py')
S = load('test_backend_sync', 'dev-tools/sync_exports.py')
C = load('test_compressed_drawio', 'scripts/check_drawio.py')
P = load('test_compressed_presentation', 'scripts/check_presentation.py')
D = load('test_drawio_pages', 'dev-tools/export_drawio.py')
X = load('test_drawio_codec', 'scripts/drawio_xml.py')
E = load('test_long_text_drawio', 'scripts/emit_drawio.py')


class LongTextLayout(unittest.TestCase):
    def setUp(self):
        self.card = {'title': '较长说明 <原文> & 边界', 'items': [
            '保留中文说明与 provider_registry、WorkflowStore；不要裁切或缩小字号。' * 6,
            '第二段仍然属于同一张卡片，段间要留白。']}

    def test_long_cards_widen_without_losing_text(self):
        layout = E.L
        cards = layout.card_rows({'cards': [self.card]}, 0, 1800, 400)
        card = cards[0]
        narrow = layout._card_entry(0, self.card, 24, 18)
        self.assertGreater(card['width'], narrow['width'])
        self.assertLess(len(card['item_lines']), len(narrow['item_lines']))
        self.assertEqual(card['item_lines'].count(''), 1)
        compact = lambda s: ''.join(s.split()).replace('•', '')
        self.assertEqual(compact(''.join(card['item_lines'])), compact(''.join(self.card['items'])))
        self.assertGreater(card['y'], 400)

    def test_narrow_canvas_stacks_cards_instead_of_squeezing_them(self):
        cards = E.L.card_rows({'cards': [self.card, self.card]}, 0, 600, 200)
        self.assertEqual(cards[0]['width'], cards[1]['width'])
        self.assertGreater(cards[1]['y'], cards[0]['y'] + cards[0]['height'])

    def test_drawio_paragraph_metrics_and_escaping(self):
        E.palette.use_backend('drawio')
        cards = E.L.card_rows({'cards': [self.card]}, 0, 1200, 0)
        cells = E.card_cells(cards, {'font_family': 'Helvetica', 'font_scale': 1})
        cell = ET.fromstring(cells[0])
        self.assertIn('line-height:1.6', cell.get('value'))
        self.assertIn('margin-bottom:18.0px', cell.get('value'))
        self.assertIn('&lt;原文&gt; &amp;', cell.get('value'))
        self.assertIn('<br><br>', cell.get('value'))
        self.assertIn('spacingLeft=24', cell.get('style'))
        self.assertEqual(float(cell.find('mxGeometry').get('height')), cards[0]['height'])


def compress(root):
    for page in root.findall('diagram'):
        model = page.find('mxGraphModel')
        raw = urllib.parse.quote(ET.tostring(model, encoding='unicode'), safe='').encode()
        encoder = zlib.compressobj(wbits=-15)
        payload = encoder.compress(raw) + encoder.flush()
        page.remove(model)
        page.text = base64.b64encode(payload).decode()
    return ET.tostring(root, encoding='unicode')


class DrawioExtensions(unittest.TestCase):
    def setUp(self):
        self.source = (BASE / 'examples/regions/diagram.drawio').read_text()

    def test_compressed_multipage_editor_roundtrip(self):
        root = ET.fromstring(self.source)
        root.set('agent', 'draw.io desktop')
        root.append(copy.deepcopy(root.find('diagram')))
        packed = compress(root)
        self.assertEqual(C.check_text(packed), [])
        self.assertEqual(P.drawio(packed), P.drawio(ET.tostring(X.parse(packed), encoding='unicode')))
        self.assertEqual(len(P.drawio(packed)), 2)

    def test_invalid_edge_inside_compressed_page_is_still_rejected(self):
        root = ET.fromstring(self.source)
        edge = next(c for c in root.iter('mxCell') if c.get('edge') == '1')
        edge.set('target', 'missing-node')
        self.assertTrue(any('missing-node' in p for p in C.check_text(compress(root))))

    def test_bad_or_oversized_compressed_payload_rejected(self):
        for content in ('not-base64!', base64.b64encode(b'not-deflate').decode()):
            self.assertTrue(C.check_text(f'<mxfile><diagram>{content}</diagram></mxfile>'))
        with patch.object(X, 'MAX_PAGE_BYTES', 20):
            with self.assertRaises(ValueError):
                X.parse(compress(ET.fromstring(self.source)))

    def test_entity_declaration_inside_compressed_page_rejected(self):
        raw = urllib.parse.quote('<!DOCTYPE mxGraphModel><mxGraphModel/>').encode()
        enc = zlib.compressobj(wbits=-15)
        data = base64.b64encode(enc.compress(raw) + enc.flush()).decode()
        self.assertTrue(C.check_text(f'<mxfile><diagram>{data}</diagram></mxfile>'))

    def test_nested_editor_geometry_is_not_mismeasured(self):
        root = ET.fromstring(self.source)
        cells = [c for c in root.iter('mxCell') if c.get('vertex') == '1']
        cells[-1].set('parent', cells[0].get('id'))
        with self.assertRaisesRegex(ValueError, '嵌套'):
            P.drawio(ET.tostring(root, encoding='unicode'))

    def test_page_selection_and_pdf_all_pages(self):
        command = D.build_command('drawio', 'a.drawio', 'a.svg', 'svg', 1, page_index=2)
        self.assertEqual(command[command.index('--page-index')+1], '2')
        self.assertNotIn('--all-pages', command)
        self.assertIn('--all-pages', D.build_command('drawio', 'a.drawio', 'a.pdf', 'pdf', 1))
        with tempfile.TemporaryDirectory() as td:
            root = ET.fromstring(self.source)
            root.append(copy.deepcopy(root.find('diagram')))
            source = Path(td) / 'a.drawio'; source.write_text(compress(root))
            with patch.object(D, 'find_binary', side_effect=AssertionError('must fail before rendering')):
                self.assertFalse(D.export(str(source), str(Path(td)/'a.svg'), fmt='svg')['ok'])
                self.assertFalse(D.export(str(source), str(Path(td)/'a.svg'), fmt='svg', page_index=3)['ok'])


class MermaidExtensions(unittest.TestCase):
    def setUp(self):
        self.spec = {'type':'flow', 'nodes':[{'id':'end', 'label':'开始', 'kind':'plain'},
                     {'id':'中文 id', 'label':'完成', 'kind':'plain'}],
                     'edges':[{'from':'end', 'to':'中文 id', 'label':'执行'}]}

    def test_deterministic_stable_ids_and_parallel_edges(self):
        self.spec['edges'].append({'from':'end', 'to':'中文 id', 'kind':'async', 'label':'通知'})
        text = M.emit(self.spec)
        self.assertEqual(text, M.emit(self.spec))
        self.assertIn(f'{M.ident("end")} -->', text)
        self.assertIn(f'{M.ident("end")} -.->', text)
        self.spec['nodes'].reverse()
        self.assertIn(M.ident('中文 id'), M.emit(self.spec))

    def test_syntax_characters_cannot_create_edges_or_html(self):
        self.spec['nodes'][0]['label'] = 'A"] --> evil["B <script>\n百分比 % 中文'
        text = M.emit(self.spec)
        self.assertNotIn('<script>', text)
        self.assertNotIn('"] --> evil["', text)
        self.assertIn('百分比', text)
        self.assertIn('<br/>', text)

    def test_groups_colors_and_cards_remain_visible(self):
        spec = json.loads((BASE/'examples/regions/source.diagram.json').read_text())
        spec['cards'] = [{'title':'说明','items':['第一条','第二条']}]
        text = M.emit(spec, colors=str(BASE/'examples/regions/project.colors.json'))
        self.assertEqual(text.count('  subgraph '), 5)
        self.assertIn('diagram_main ~~~ diagram_notes', text)
        self.assertEqual(text.count('  style g'), 3)
        self.assertIn('第一条', text)
        self.assertIn('第二条', text)
        for node in spec['nodes']:
            self.assertIn(node['label'], text)

    def test_state_uses_native_state_grammar_and_keeps_back_edge(self):
        spec = json.loads((BASE/'examples/state/source.diagram.json').read_text())
        text = M.emit(spec)
        self.assertIn('stateDiagram-v2', text)
        self.assertIn(f'{M.ident("review")} --> {M.ident("draft")} : 退回修改', text)

    def test_unsupported_contracts_are_not_silently_dropped(self):
        for key, value in [('rank',0), ('pin','top'), ('icon','server')]:
            spec = copy.deepcopy(self.spec); spec['nodes'][0][key] = value
            with self.assertRaises(ValueError): M.emit(spec)
        for kind in ('network','mindmap'):
            spec = copy.deepcopy(self.spec); spec['type'] = kind
            with self.assertRaises(ValueError): M.emit(spec)
        spec = copy.deepcopy(self.spec); spec['type']='state'
        spec['edges'][0]['kind']='optional'
        with self.assertRaises(ValueError): M.emit(spec)

    def test_bad_reference_is_rejected(self):
        self.spec['edges'][0]['to']='missing'
        with self.assertRaises(ValueError): M.emit(self.spec)

    def test_notes_follow_main_graph_without_creating_business_edges(self):
        self.spec['direction'] = 'LR'
        self.spec['cards'] = [{'title': '说明', 'items': ['中文说明' * 30, '下一段 <保留>']}]
        text = M.emit(self.spec)
        self.assertIn('flowchart TB\n  subgraph diagram_main', text)
        self.assertIn('direction LR', text)
        self.assertEqual(text.count(' -->'), 1)
        self.assertEqual(text.count(' ~~~ '), 1)
        self.assertIn('<br/>\u200b<br/>', text)
        self.assertIn('class card0 diagram_note', text)
        self.assertIn('text-anchor:start', text)
        self.assertNotIn('<保留>', text)
        self.assertIn('#60;保留#62;', text)

    def test_no_notes_keeps_original_direction_without_wrappers(self):
        self.spec['direction'] = 'LR'
        self.spec['nodes'][0]['detail'] = '较长中文说明 mixed English details ' * 5
        text = M.emit(self.spec)
        self.assertIn('flowchart LR', text)
        self.assertNotIn('diagram_main', text)
        self.assertIn('<br/>', text)
        self.assertIn('"wrappingWidth": 800', text)

    def test_source_only_creates_no_export_or_recipe(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'a.mmd'; source.write_text(M.emit(self.spec))
            with patch.object(S,'load_exporter',side_effect=AssertionError('renderer loaded')):
                self.assertEqual(S.sync(source)['status'],'not-requested')
            self.assertEqual([p.name for p in Path(td).iterdir()], ['a.mmd'])

    def test_svg_only_sync_retains_padding_and_avoids_png(self):
        calls=[]
        def export(source,out,fmt,**options):
            calls.append((fmt,options)); Path(out).write_text('new SVG');return {'ok':True}
        engine=SimpleNamespace(DEFAULT_PADDING=80,export=export)
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'a.mmd'; source.write_text('flowchart TB\nA-->B')
            source.with_suffix('.svg').write_text('old SVG')
            with patch.object(S,'load_exporter',return_value=engine):
                self.assertTrue(S.sync(source,padding=96)['ok'])
                self.assertTrue(S.sync(source)['ok'])
            self.assertEqual([c[0] for c in calls],['svg','svg'])
            self.assertEqual(calls[-1][1]['padding'],96)
            self.assertFalse(source.with_suffix('.png').exists())

    def test_ambiguous_mermaid_and_other_native_basename_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'a.mmd'; source.write_text('flowchart TB\nA-->B')
            source.with_suffix('.drawio').write_text('<mxfile/>')
            with patch.object(S,'load_exporter',side_effect=AssertionError('renderer loaded')):
                self.assertFalse(S.sync(source,['svg'])['ok'])

    def test_official_parser_mode_returns_no_images(self):
        payload = base64.b64encode(json.dumps({'ok':True,'stage':'syntax','rendered':False}).encode()).decode()
        engine=SimpleNamespace(find_browser=lambda x:'/browser',_dump_dom=lambda *a:f'<pre id="result">{payload}</pre>')
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'a.mmd'; source.write_text(M.emit(self.spec))
            with patch.object(R,'browser_tools',return_value=engine):
                result=R.run(source)
            self.assertTrue(result['ok']); self.assertFalse(result['rendered'])
            self.assertEqual(len(list(Path(td).iterdir())),1)

    def test_invalid_export_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'a.mmd'; source.write_text('invalid source')
            target=Path(td)/'a.svg'; target.write_text('old')
            with patch.object(R,'run',return_value={'ok':False,'message':'parse error'}):
                self.assertFalse(R.export(source,target,fmt='svg')['ok'])
            self.assertEqual(target.read_text(),'old')


if __name__ == '__main__':
    unittest.main()
