from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SKILL=Path(__file__).resolve().parents[2]/'skills/diagram-authoring'
s=importlib.util.spec_from_file_location('render_review',SKILL/'dev-tools/check_render.py')
R=importlib.util.module_from_spec(s);s.loader.exec_module(R)

def observation():
    return {'canvas':{'x':0,'y':0,'width':800,'height':600},
      'texts':[{'text':'检查','box':{'x':10,'y':10,'width':50,'height':24},'font':'Helvetica','px':24,'cell':None}],
      'graphics':[{'kind':'path','box':{'x':10,'y':40,'width':80,'height':30}}],
      'arrows':[3], 'cells':[], 'font_status':'loaded','fonts':[{'family':'Helvetica','available':True}], 'failed_faces':[]}
WANT={'backend':'excalidraw','labels':['检查'],'arrows':1,'cells':{}}

class RenderReviewTests(unittest.TestCase):
    def codes(self,want,observed,**kw):
        return {f['code'] for f in R.assess(want,observed,**kw)['findings']}
    def test_complete_observation_passes_without_claiming_unmeasured_properties(self):
        result=R.assess(WANT,observation(),preset='slide-16x9')
        self.assertEqual(result['status'],'pass');self.assertTrue(result['limits'])
    def test_cropped_label_or_path_fails(self):
        obs=observation();obs['texts'][0]['box']['x']=-20
        self.assertIn('render/canvas-clipping',self.codes(WANT,obs))
        obs=observation();obs['graphics'][0]['box']['y']=590
        self.assertIn('render/canvas-clipping',self.codes(WANT,obs))
    def test_missing_arrowhead_and_deleted_arrow_fail(self):
        for paths in ([2],[]):
            obs=observation();obs['arrows']=paths
            self.assertIn('render/arrow-inventory',self.codes(WANT,obs))
    def test_duplicate_labels_preserve_multiplicity(self):
        want=deepcopy(WANT);want['labels'].append('检查')
        self.assertIn('render/label-missing',self.codes(want,observation()))
    def test_unavailable_font_and_failed_fontface_fail(self):
        for fail in ('missing','face'):
            obs=observation()
            if fail=='missing':obs['fonts'][0]['available']=False
            else:obs['failed_faces']=['MissingFont']
            self.assertIn('render/font-unavailable',self.codes(WANT,obs))
    def test_actual_target_size_and_small_text_are_separate_findings(self):
        obs=observation();obs['texts'][0]['px']=12
        codes=self.codes(WANT,obs,preset='slide-16x9',width=1280)
        self.assertIn('render/small-text',codes);self.assertIn('render/size',codes)
    def test_internal_clip_overlap_and_occlusion_are_distinct_findings(self):
        for field, code in (('clipped','internal-clipping'), ('overlaps','text-overlap'), ('occluded','text-occluded')):
            obs=observation();obs[field]=[{'text':'检查'}]
            self.assertIn('render/'+code,self.codes(WANT,obs))
    def test_scrolling_document_pass_does_not_imply_full_frame_readability(self):
        obs=observation();obs['canvas'].update(width=1200,height=2400)
        obs['texts'][0]['px']=12
        self.assertNotIn('render/small-text',self.codes(WANT,obs,preset='doc-wide'))
        self.assertIn('render/small-text',self.codes(WANT,obs,preset='slide-16x9'))
    def test_drawio_ids_check_missing_cell_or_changed_text(self):
        want={'backend':'drawio','labels':[],'cells':{'n-a':'检查'},'edges':['e-0']}
        obs=observation();obs['texts'][0]['cell']='n-a';obs['cells']=[{'id':'e-0','paths':2}]
        self.assertFalse(self.codes(want,obs))
        obs['texts'][0]['text']='别的文字';obs['cells'][0]['paths']=1
        codes=self.codes(want,obs)
        self.assertIn('render/label-missing',codes);self.assertIn('render/arrow-inventory',codes)
    def test_svg_active_content_rejected_and_standard_dtd_removed(self):
        for svg in ('<svg><script>alert(1)</script></svg>','<svg onload="x()"/>',
                    '<svg><image href="https://example.com/a.png"/></svg>',
                    '<!DOCTYPE svg [<!ENTITY x "a">]><svg/>'):
            with self.assertRaises(ValueError):R.safe_svg(svg)
        self.assertEqual(R.safe_svg('<!DOCTYPE svg PUBLIC "a" "b"><svg/>'),'<svg/>')
    def test_missing_browser_is_skipped_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            svg=Path(td)/'x.svg';svg.write_text('<svg/>')
            with patch.object(R.EXPORT,'find_browser',return_value=None):
                result=R.inspect(SKILL/'examples/flow/diagram.excalidraw',svg)
            self.assertEqual(result['status'],'skipped')
    def test_sources_extract_actual_visible_inventory(self):
        for backend in ('excalidraw','drawio'):
            result=R.expected(SKILL/f'examples/flow/diagram.{backend}')
            self.assertEqual(result['backend'],backend)
            self.assertEqual(result.get('arrows',len(result.get('edges',[]))),3)

if __name__=='__main__':unittest.main()
