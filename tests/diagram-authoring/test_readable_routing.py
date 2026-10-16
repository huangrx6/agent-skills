"""Actual readability failures: close lanes, excess bends, text near frames."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[2]/'skills/diagram-authoring'
def load(name):
    s=importlib.util.spec_from_file_location('readable_test_'+name, ROOT/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
R,L,E,D=load('readable_routing'),load('layout'),load('emit_excalidraw'),load('emit_drawio')


class ReadableRoutingTests(unittest.TestCase):
    def test_stacked_regions_reserve_outer_space_in_both_backends_even_with_return_edge(self):
        source={'type':'architecture','direction':'TB',
                'nodes':[{'id':n,'label':n,'kind':'service','rank':i,'group':'g'+n}
                         for i,n in enumerate('abc')],
                'groups':[{'id':'g'+n,'label':label} for n,label in
                          [('a','应用层'),('b','一段需要换行的能力层标题说明'),('c','提供层')]],
                'edges':[{'from':'a','to':'b','label':'调用'},
                         {'from':'b','to':'c','label':'保存'},
                         {'from':'c','to':'a','label':'回调','kind':'async'}]}
        original=deepcopy(source)
        for emitter in (E,D):
            artifact,result,outcome,*_=emitter.emit(source,preset='doc-wide')
            self.assertTrue(artifact,[i.line() for i in outcome.issues])
            boxes=emitter.L.boxes_from_spec(source,presentation='doc-wide')
            regions=emitter.L.region_boxes(source,result.placed,boxes,presentation='doc-wide')
            self.assertEqual(len(result.edges),3)
            self.assertTrue(result.reversed_edges)
            gaps=list(R.region_vertical_gaps(regions))
            self.assertTrue(gaps)
            self.assertTrue(all(gap>=79.9 for _,_,gap in gaps),gaps)
            self.assertTrue(all(r['label_y']-r['y']>=18 for r in regions))
        self.assertEqual(source,original)

    def test_internal_ranks_of_one_group_do_not_gain_exterior_corridors(self):
        source={'type':'architecture','direction':'TB',
                'nodes':[{'id':n,'label':n,'kind':'service','rank':i,'group':'same'}
                         for i,n in enumerate('abc')],
                'groups':[{'id':'same','label':'同一区域'}],
                'edges':[{'from':'a','to':'b'},{'from':'b','to':'c'}]}
        boxes=L.boxes_from_spec(source)
        before=L.layout(source,boxes)
        after=L.layout(source,boxes,presentation='doc-wide')
        self.assertEqual(before.placed,after.placed)

    def test_region_gap_audit_ignores_side_by_side_and_nested_frames(self):
        scene={'elements':[{'id':'region-a','type':'rectangle','x':0,'y':0,'width':200,'height':100},
                           {'id':'region-b','type':'rectangle','x':0,'y':109,'width':200,'height':100},
                           {'id':'region-c','type':'rectangle','x':230,'y':0,'width':200,'height':100}]}
        findings=[f for f in R.assess_scene(scene,L)['findings'] if f['code']=='region-clearance']
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]['gap'],9)
        scene['elements'][1].update(x=20,y=20,width=100,height=40)
        self.assertFalse(R.assess_scene(scene,L)['findings'])

    def test_header_search_finds_clear_slot_between_actual_lines(self):
        region={'x':0,'y':0,'width':800,'label_y':18,'label_width':160,'label_height':28}
        lines=[[[x,0],[x,100]] for x in (141,329,452,510,672)]
        x,y,dirty=R.place_region_title(region,lines)
        self.assertFalse(dirty)
        self.assertTrue(all(not R._hits_rect(*line,(x,y,160,28),9.9) for line in lines))

    def test_crossings_are_detected_without_optional_origin_metadata(self):
        edges=[{'points':[[0,50],[100,50]]},{'points':[[50,0],[50,100]]}]
        self.assertEqual(L.geometric_crossing_pairs(edges),[[0,1]])

    def test_crossing_at_an_interior_waypoint_is_not_a_shared_endpoint(self):
        edges=[{'points':[[0,50],[100,50]]},{'points':[[50,0],[50,50],[50,100]]}]
        self.assertEqual(L.geometric_crossing_pairs(edges),[[0,1]])
        self.assertFalse(L._polylines_cross([[0,0],[100,0]],[[100,0],[100,100]]))

    def test_close_parallel_lines_differ_from_nonoverlapping_spans(self):
        edges=[{'points':[[0,0],[100,0]]},{'points':[[0,12],[100,12]]}]
        self.assertEqual(R.parallel_conflicts(edges)[0]['gap'],12)
        edges[1]['points']=[[120,12],[220,12]]
        self.assertFalse(R.parallel_conflicts(edges))

    def test_label_has_space_to_relationship_lines_and_region_border(self):
        own=[[0,0],[200,0]];border=[[0,-18],[200,-18]]
        x,y,dirty=R.place_label(own,80,16,[own,border],[])
        self.assertFalse(dirty)
        self.assertGreaterEqual(y,9.9)  # above is too crowded; place below
        for line in (own,border):
            self.assertFalse(R._hits_rect(*line,(x,y,80,16),9.8))

    def test_unresolved_label_position_is_not_reported_as_clean(self):
        _,_,dirty=R.place_label([[0,0],[20,0]],40,16,[[[0,0],[20,0]]],[(-1000,-1000,2000,2000)])
        self.assertTrue(dirty)

    def test_exclusive_parallel_branches_align_together_without_changing_order(self):
        nodes=[{'id':n,'label':n,'kind':'service'} for n in 'abcds']
        table={'a':L.Placed('a',200,0,100,80,0),'b':L.Placed('b',400,0,100,80,0),
               'c':L.Placed('c',100,240,100,80,1),'d':L.Placed('d',300,240,100,80,1),
               's':L.Placed('s',0,0,100,80,0)}
        edges=[{'from':'a','to':'c'},{'from':'b','to':'d'},{'from':'s','to':'c'},{'from':'s','to':'d'}]
        result=L.LayoutResult('TB',{}, {},{},table,edges,0,[],0,[],[])
        R.align_exclusive_parents({'nodes':nodes},result,L)
        self.assertEqual(result.placed['c'].x,200)
        self.assertEqual(result.placed['d'].x,400)

    def test_native_audit_detects_text_close_to_region_outline(self):
        scene={'elements':[{'id':'region-x','type':'rectangle','x':0,'y':0,'width':200,'height':100},
                           {'id':'elabel-e','type':'text','x':60,'y':-4,'width':60,'height':16,'text':'近边框'}]}
        self.assertEqual(R.assess_scene(scene,L)['findings'][0]['code'],'label-clearance')

    def test_reading_preset_preserves_edge_labels_in_both_backends(self):
        source=json.loads((ROOT/'examples/regions/source.diagram.json').read_text())
        colors=json.loads((ROOT/'examples/regions/project.colors.json').read_text())
        scene,result,outcome,*_=E.emit(source,colors=colors,preset='doc-wide',quality='showcase')
        self.assertTrue(scene,[i.line() for i in outcome.issues])
        self.assertEqual(len(result.edges),len(source['edges']))
        self.assertTrue(all('origin' in e for e in result.edges))
        self.assertEqual(R.assess_scene(scene,L)['status'],'pass')
        xml,*_=D.emit(source,colors=colors,preset='doc-wide',quality='showcase')
        self.assertIn('as="offset"',xml)
        for edge in source['edges']: self.assertIn(edge['label'],xml)

    def test_large_slide_annotations_get_room_before_placement(self):
        source=json.loads((ROOT/'examples/presentation/source.diagram.json').read_text())
        scene,result,outcome,*_=E.emit(source,preset='slide-16x9',quality='showcase')
        self.assertTrue(scene,[i.line() for i in outcome.issues])
        self.assertEqual(R.assess_scene(scene,L)['status'],'pass')
        # An annotation intruding into a node must not pass merely because
        # it clears the relationship's centre line.
        label=next(e for e in scene['elements'] if e['id'].startswith('elabel-'))
        node=next(e for e in scene['elements'] if e['id'].startswith('node-'))
        label['x'],label['y']=node['x'],node['y']
        self.assertIn('label-node-clearance',[f['code'] for f in R.assess_scene(scene,L)['findings']])


if __name__=='__main__': unittest.main()
