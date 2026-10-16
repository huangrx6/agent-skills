"""Regression contracts for per-generation typography, not wording snapshots."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

SKILL=Path(__file__).resolve().parents[2]/'skills/diagram-authoring'
def load(name):
    s=importlib.util.spec_from_file_location('presentation_test_'+name,SKILL/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
E,D,P=load('emit_excalidraw'),load('emit_drawio'),load('check_presentation')

def sample(name='flow'):
    return json.loads((SKILL/f'examples/{name}/source.diagram.json').read_text())

class PresentationContextTests(unittest.TestCase):
    def test_default_business_geometry_matches_frozen_editable_examples(self):
        for kind in ('architecture','flow','dependency','state','mindmap','network'):
            with self.subTest(kind=kind):
                spec=sample(kind)
                scene,*_=E.emit(spec,quality='showcase')
                xml,*_=D.emit(spec,scheme='classic',quality='showcase')
                self.assertEqual(scene,json.loads((SKILL/f'examples/{kind}/diagram.excalidraw').read_text()))
                # Historical previews keep their reviewed card typography.
                # Business geometry remains frozen; cards have separate layout tests.
                actual = ET.fromstring(xml)
                frozen = ET.fromstring((SKILL/f'examples/{kind}/diagram.drawio').read_text())
                for root in (actual, frozen):
                    cells = root.find('.//root')
                    for cell in list(cells):
                        if cell.get('id', '').startswith('card-'):
                            cells.remove(cell)
                self.assertEqual(ET.tostring(actual), ET.tostring(frozen))

    def test_context_is_immutable_and_unknown_preset_fails(self):
        ctx=E.L.P.resolve('slide-16x9')
        with self.assertRaises(FrozenInstanceError):ctx.detail=4
        with self.assertRaises(ValueError):E.emit(sample(),preset='made-up')
        with self.assertRaises(ValueError):D.emit(sample(),preset='made-up')

    def test_slide_then_document_does_not_leak_settings_or_mutate_input(self):
        spec=sample();before=deepcopy(spec)
        for emitter in (E,D):
            plain,*_=emitter.emit(spec)
            slide,*_=emitter.emit(spec,preset='slide-16x9')
            again,*_=emitter.emit(spec)
            self.assertTrue(slide);self.assertNotEqual(slide,plain);self.assertEqual(plain,again)
        self.assertEqual(spec,before)
        self.assertEqual(E.tm.FONT_DETAIL,12)

    def test_detail_measurement_and_renderer_use_same_font(self):
        spec=sample('state');spec['nodes'][0]['detail']='支持中文 English detail 的多行说明，包含必要信息。'
        scene,layout,outcome,_=E.emit(spec,preset='slide-16x9')
        self.assertFalse(outcome.blocking)
        details=[e for e in scene['elements'] if e['type']=='text' and e['id'].startswith('detail-')]
        self.assertTrue(details);self.assertTrue(all(e['fontSize']==20 for e in details))
        xml,*_=D.emit(spec,preset='slide-16x9',scheme='classic')
        root=ET.fromstring(xml)
        self.assertIn('font-size:20px',root.find('.//UserObject[@id="n-draft"]').get('label'))
        measured=P.drawio(xml)
        self.assertTrue(any(':span-' in ident and size==20 for _,_,fonts in measured for ident,size in fonts))

    def test_title_region_edge_card_and_node_roles_all_use_preset(self):
        spec=sample('architecture');spec['cards']=[{'title':'结论','items':['保留全部关系。']}]
        scene,_,outcome,_=E.emit(spec,preset='slide-16x9')
        self.assertTrue(scene);self.assertFalse(outcome.blocking)
        for prefix,size in [('diagram-title',32),('region-label',24),('elabel-',20),('card-title',24),('card-items',20)]:
            found=[e for e in scene['elements'] if e['type']=='text' and e['id'].startswith(prefix)]
            self.assertTrue(found,prefix);self.assertTrue(all(e['fontSize']==size for e in found),prefix)

    def test_multi_page_drawio_keeps_each_pages_sizes(self):
        doc,*_=D.emit_page(sample(),preset='doc-inline',scheme='classic')
        slide,*_=D.emit_page(sample(),preset='slide-16x9',scheme='classic')
        pages=P.drawio(D.build_file([doc,slide]))
        self.assertEqual(min(size for _,size in pages[0][2]),12)
        self.assertEqual(min(size for _,size in pages[1][2]),20)

    def test_print_preset_changes_all_secondary_fonts_without_parsing_label_as_css(self):
        spec=sample();spec['nodes'][0]['label']='font-size:1px'
        scene,*_=E.emit(spec,preset='print-a4-landscape')
        self.assertEqual(min(e['fontSize'] for e in scene['elements'] if e['type']=='text'),14)
        xml,*_=D.emit(spec,preset='print-a4-landscape',scheme='classic')
        self.assertEqual(min(size for _,_,fonts in P.drawio(xml) for _,size in fonts),14)

    def test_slide_uses_new_spacing_and_keeps_every_relation(self):
        spec=sample();plain,base,*_=E.emit(spec)
        slide,result,outcome,_=E.emit(spec,preset='slide-16x9',quality='showcase')
        self.assertTrue(slide);self.assertFalse(outcome.blocking)
        self.assertNotEqual(base.params['rankSeparation'],result.params['rankSeparation'])
        self.assertEqual(len([e for e in slide['elements'] if e['type']=='arrow']),len(spec['edges']))
        self.assertEqual(P.assess(P.excalidraw(json.dumps(slide)),'slide-16x9')['pages'][0]['status'],'pass')
        self.assertEqual(P.assess(P.excalidraw(json.dumps(plain)),'slide-16x9')['pages'][0]['status'],'warning')

    def test_unfit_target_returns_actionable_finding_without_deleting_content(self):
        spec=sample('architecture')
        for emitter in (E,D):
            artifact,result,outcome,_=emitter.emit(spec,preset='slide-16x9',quality='showcase')
            self.assertTrue(artifact)
            self.assertEqual(len(result.edges),len(spec['edges']))
            issues=[i for i in outcome.issues if i.check=='presentation']
            self.assertTrue(issues);self.assertFalse(issues[0].blocking)
            self.assertEqual(issues[0].evidence['basis'],'editable_geometry_estimate')

if __name__=='__main__':unittest.main()
