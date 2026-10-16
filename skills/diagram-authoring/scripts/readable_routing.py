"""Bounded routing refinement for explicit reading presets.

Works on forward, unfolded layered graphs; preserves edge identity/direction.
It does not merge edges, invent buses or change the structure specification.
"""
from copy import deepcopy
from dataclasses import replace
from statistics import median
import math

LINE_CLEARANCE = 24.0
TEXT_CLEARANCE = 10.0
FRAME_CLEARANCE = 18.0
NODE_CLEARANCE = 16.0


def region_clearance(presentation):
    """Visible inter-region whitespace, independent of node padding."""
    return max(80., presentation.region * 4,
               presentation.detail * 1.4 + 2 * TEXT_CLEARANCE + 2 * FRAME_CLEARANCE)


def region_vertical_gaps(regions):
    """Disjoint, vertically stacked envelopes with overlapping horizontal spans."""
    for i,a in enumerate(regions):
        for b in regions[i+1:]:
            if min(a['x']+a['width'],b['x']+b['width']) <= max(a['x'],b['x']):
                continue
            upper,lower=sorted((a,b),key=lambda r:r['y'])
            gap=lower['y']-upper['y']-upper['height']
            if gap >= -.1:
                yield upper,lower,round(gap,2)


def reserve_region_corridors(spec, placed, boxes, L, presentation):
    """Expand only boundaries between disjoint rank ranges, then route normally.

    Works before edge routing, including graphs with a return edge. It moves
    complete rank suffixes (and their invisible dummy nodes), preserving facts,
    order and internal group spacing. Folded/radial layouts do not call this.
    """
    ctx=L.P.resolve(presentation)
    table=dict(placed)
    for boundary in sorted({p.rank for p in table.values()})[1:]:
        regions=L.region_boxes(spec,table,boxes,presentation=ctx)
        ranges={r['id']:(min(table[n].rank for n in r['members']),
                         max(table[n].rank for n in r['members'])) for r in regions}
        # Long cross-layer relations consume routing space too. Bound the
        # allowance so density is not answered with unlimited whitespace.
        lanes=0
        for edge in spec.get('edges',[]):
            a,b=table[edge['from']],table[edge['to']]
            if min(a.rank,b.rank) < boundary <= max(a.rank,b.rank):
                if abs(a.x+a.width/2-b.x-b.width/2)>LINE_CLEARANCE:
                    lanes+=1
        target=region_clearance(ctx)+min(max(lanes-1,0),3)*LINE_CLEARANCE
        shift=0.
        for upper in regions:
            if ranges[upper['id']][1] >= boundary: continue
            for lower in regions:
                if ranges[lower['id']][0] != boundary: continue
                if min(upper['x']+upper['width'],lower['x']+lower['width']) <= max(upper['x'],lower['x']): continue
                gap=lower['y']-upper['y']-upper['height']
                shift=max(shift,target-gap)
        if shift>.1:
            table={n:replace(p,y=round(p.y+shift,2)) if p.rank>=boundary else p
                   for n,p in table.items()}
    return table


def _axis_segments(points):
    for a, b in zip(points, points[1:]):
        if abs(a[0] - b[0]) < .5:
            yield 0, a[0], min(a[1], b[1]), max(a[1], b[1])
        elif abs(a[1] - b[1]) < .5:
            yield 1, a[1], min(a[0], b[0]), max(a[0], b[0])


def parallel_conflicts(edges, clearance=LINE_CLEARANCE):
    """Long parallel spans too close to follow; shared endpoints aren't exempt."""
    found = []
    segments = [list(_axis_segments(e['points'])) for e in edges]
    for i, first in enumerate(segments):
        for j in range(i + 1, len(segments)):
            for a in first:
                for b in segments[j]:
                    overlap = min(a[3], b[3]) - max(a[2], b[2])
                    gap = abs(a[1] - b[1])
                    if a[0] == b[0] and overlap > 24 and gap < clearance - .1:
                        found.append({'edges': [i, j], 'gap': round(gap, 2), 'overlap': round(overlap, 2)})
    return found


def frame_lines(regions):
    return [[[r['x'], r['y']], [r['x'] + r['width'], r['y']],
             [r['x'] + r['width'], r['y'] + r['height']],
             [r['x'], r['y'] + r['height']], [r['x'], r['y']]] for r in regions]


def title_boxes(regions):
    # Reserve a readable left-aligned title in each region's header.
    return [(r['x'] + 12, r['label_y'], r['label_width'], r['label_height'])
            for r in regions if r.get('label')]


def _hits_rect(a, b, rect, pad=0):
    x, y, w, h = rect
    lo, hi = 0., 1.
    for start, delta, low, high in ((a[0], b[0]-a[0], x-pad, x+w+pad),
                                    (a[1], b[1]-a[1], y-pad, y+h+pad)):
        if abs(delta) < 1e-9:
            if not low < start < high:
                return False
        else:
            t1, t2 = sorted(((low-start)/delta, (high-start)/delta))
            lo, hi = max(lo, t1), min(hi, t2)
            if lo >= hi:
                return False
    return True


def score(result, regions, L):
    edges, placed = result.edges, result.placed
    through = sum(len(L.nodes_hit_by_polyline(e['points'], placed, {e['from'], e['to']})) for e in edges)
    own = sum(L._crosses_own_nodes(e['points'], placed, e['from'], e['to']) for e in edges)
    node_near = sum(_hits_rect(a,b,(p.x,p.y,p.width,p.height),NODE_CLEARANCE)
                    for e in edges for a,b in zip(e['points'],e['points'][1:])
                    for key,p in result.real_nodes().items() if key not in (e['from'],e['to']))
    slant = sum(L._is_slanted(e['points']) for e in edges)
    headers = title_boxes(regions)
    title_hits = sum(_hits_rect(a, b, r, TEXT_CLEARANCE) for e in edges for a,b in zip(e['points'],e['points'][1:]) for r in headers)
    border_near = 0
    frames = [s for p in frame_lines(regions) for s in _axis_segments(p)]
    for e in edges:
        for a in _axis_segments(e['points']):
            border_near += sum(a[0] == b[0] and abs(a[1]-b[1]) < FRAME_CLEARANCE and min(a[3],b[3])-max(a[2],b[2]) > 28 for b in frames)
    parallel = parallel_conflicts(edges)
    overlap = sum(p['gap'] < .75 for p in parallel)
    bends = sum(max(0,len(e['points'])-2) for e in edges)
    length = sum(math.dist(a,b) for e in edges for a,b in zip(e['points'],e['points'][1:]))
    return (through, own, slant, len(L.geometric_crossing_pairs(edges)), overlap,
            node_near, title_hits, len(parallel), border_near, bends, round(length, 1))


def align_exclusive_parents(spec, result, L):
    """Align parallel single-target branches as a batch, respecting row order."""
    axis = 0 if result.direction == 'TB' else 1
    parent, children = {}, {}
    for edge in result.edges:
        parent.setdefault(edge['to'], []).append(edge['from'])
        children.setdefault(edge['from'], []).append(edge['to'])
    centre = lambda p: (p.x+p.width/2) if axis == 0 else (p.y+p.height/2)
    size = lambda p: p.width if axis == 0 else p.height
    pinned = {n['id'] for n in spec['nodes'] if n.get('pin')}
    for rank in sorted({p.rank for p in result.real_nodes().values()}):
        row = sorted((p for p in result.real_nodes().values() if p.rank == rank), key=centre)
        proposed = {}
        for node in row:
            exclusive = [result.placed[n] for n in parent.get(node.id, [])
                         if len(children.get(n, [])) == 1 and result.placed[n].rank == rank-1]
            if exclusive and node.id not in pinned:
                wanted = median(centre(n) for n in exclusive)
                proposed[node.id] = replace(node, **({'x':round(wanted-node.width/2,2)} if axis == 0 else {'y':round(wanted-node.height/2,2)}))
        trial = [proposed.get(n.id,n) for n in row]
        if any(centre(b)-centre(a)-(size(a)+size(b))/2 < L.NODE_CLEARANCE for a,b in zip(trial,trial[1:])):
            continue
        result.placed.update(proposed)


def _ports(node, direction, outgoing):
    """Prefer centre, then separated face slots, then side entries."""
    if direction == 'TB':
        y = node.y + node.height if outgoing else node.y
        ports = [[node.x+node.width*f,y] for f in (.5,.75,.25,.9,.1)]
        if not outgoing:
            ports += [[node.x,node.y+node.height*.5], [node.x+node.width,node.y+node.height*.5]]
        return ports
    x = node.x+node.width if outgoing else node.x
    ports = [[x,node.y+node.height*f] for f in (.5,.75,.25,.9,.1)]
    if not outgoing:
        ports += [[node.x+node.width*.5,node.y], [node.x+node.width*.5,node.y+node.height]]
    return ports


def _valid_path(path, edge, placed, L):
    if L._is_slanted(path) or L._crosses_own_nodes(path, placed, edge['from'],edge['to']):
        return False
    if L.nodes_hit_by_polyline(path, placed, {edge['from'],edge['to']}):
        return False
    if any(math.dist(a,b) < L.EDGE_MIN for a,b in zip(path,path[1:])):
        return False
    for anchor,near,key in ((path[0],path[1],edge['from']),(path[-1],path[-2],edge['to'])):
        normal=L._outward_normal(anchor,placed[key])
        if normal is None or normal[0]*(near[0]-anchor[0])+normal[1]*(near[1]-anchor[1]) <= 0:
            return False
    return True


def refine(spec, original, boxes, L, presentation):
    if original.direction not in ('TB','LR') or original.reversed_edges:
        return original
    axis = 1 if original.direction == 'TB' else 0
    main = lambda p: p.y if axis == 1 else p.x
    if any(main(original.placed[e['to']]) <= main(original.placed[e['from']]) for e in original.edges):
        return original  # folded layouts and cycles retain their existing router
    result = deepcopy(original)
    align_exclusive_parents(spec,result,L)
    result.edges=L.route_edges([dict(e, _cycle_reversed=False) for e in original.edges], [],result.placed,result.direction,set(),align=False)
    L._spread_lanes(result.edges,result.placed,result.direction)
    regions=L.region_boxes(spec,result.placed,boxes,presentation=presentation)
    # Fixed-order coordinate descent; a finite number of candidates and rounds.
    for _ in range(2):
        changed=False
        for index,edge in enumerate(result.edges):
            before=edge['points']; best=score(result,regions,L); choice=before
            src,dst=result.placed[edge['from']],result.placed[edge['to']]
            starts=[before[0]]+_ports(src,result.direction,True)
            ends=[before[-1]]+_ports(dst,result.direction,False)
            for start in starts:
                for end in ends:
                    candidates=[[start,end]]
                    if axis == 1:
                        candidates += [[start,[start[0],end[1]],end]]
                    else:
                        candidates += [[start,[end[0],start[1]],end]]
                    low,high=sorted((start[axis],end[axis]))
                    for fraction in (.5,.35,.65,.2,.8):
                        lane=low+(high-low)*fraction
                        if axis==1:
                            candidates.append([start,[start[0],lane],[end[0],lane],end])
                        else:
                            candidates.append([start,[lane,start[1]],[lane,end[1]],end])
                    for path in candidates:
                        path=L._simplify_path(path)
                        if len(path)<2 or not _valid_path(path,edge,result.placed,L):
                            continue
                        edge['points']=path
                        rank=score(result,regions,L)
                        if rank < best:
                            best,choice=rank,deepcopy(path)
            edge['points']=choice
            changed |= choice != before
        if not changed:
            break
    old_regions=L.region_boxes(spec,original.placed,boxes,presentation=presentation)
    return result if score(result,regions,L) < score(original,old_regions,L) else original


def place_region_title(region, polylines, clearance=TEXT_CLEARANCE):
    """Search within the header; report an unresolved collision explicitly."""
    width,height=region['label_width'],region['label_height']
    left=region['x']+12; right=region['x']+region['width']-12-width
    left=min(left,right)
    best=None
    y=region['label_y']
    candidates=[left+(right-left)*t for t in (0.,1.,.5,.25,.75,.125,.875,.375,.625)]
    # Fixed fractions can miss a perfectly usable gap in a dense header.
    # Add positions just outside each line's footprint in this title band.
    for line in polylines:
        for a,b in zip(line,line[1:]):
            low,high=y-clearance,y+height+clearance
            dy=b[1]-a[1]
            if abs(dy)<1e-9:
                if not low<=a[1]<=high: continue
                xs=[a[0],b[0]]
            else:
                t0,t1=sorted(((low-a[1])/dy,(high-a[1])/dy))
                t0,t1=max(0.,t0),min(1.,t1)
                if t0>t1: continue
                xs=[a[0]+(b[0]-a[0])*t for t in (t0,t1)]
            candidates.extend(x for x in (min(xs)-width-clearance-.1,max(xs)+clearance+.1)
                              if left<=x<=right)
    for x in candidates:
        hits=sum(_hits_rect(a,b,(x,y,width,height),clearance) for p in polylines for a,b in zip(p,p[1:]))
        if best is None or hits < best[0]: best=(hits,x,y)
        if not hits: break
    return round(best[1],2),round(best[2],2),bool(best[0])


def place_label(points, width, height, polylines, keepouts, clearance=TEXT_CLEARANCE):
    """Place next to a straight span, with measured space to all lines/frames."""
    spans=sorted(zip(points,points[1:]),key=lambda ab:-math.dist(*ab))
    best=None
    for extra in (0.,8.,16.,24.,40.):
        for a,b in spans:
            length=math.dist(a,b)
            if length < 1: continue
            ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
            normals=[(-uy,ux),(uy,-ux)]
            normals.sort(key=lambda n:(n[1],n[0]))
            for frac in (.5,.35,.65,.375,.625,.25,.75,.2,.8):
                mid=(a[0]+(b[0]-a[0])*frac,a[1]+(b[1]-a[1])*frac)
                for nx,ny in normals:
                    reach=abs(nx)*width/2+abs(ny)*height/2+clearance+extra
                    x,y=mid[0]+nx*reach-width/2,mid[1]+ny*reach-height/2
                    rect=(x,y,width,height)
                    line_hits=sum(_hits_rect(c,d,rect,clearance-.1) for p in polylines for c,d in zip(p,p[1:]))
                    box_hits=sum(x-clearance < r+w and x+width+clearance > r and y-clearance < s+h and y+height+clearance > s for r,s,w,h in keepouts)
                    penalty=line_hits+box_hits*10
                    if best is None or penalty < best[0]: best=(penalty,x,y)
                    if not penalty: return round(x,2),round(y,2),False
    return (round(best[1],2),round(best[2],2),bool(best[0])) if best else (points[0][0],points[0][1],True)


def path_midpoint(points):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    remaining=sum(lengths)/2
    for (a,b),length in zip(zip(points,points[1:]),lengths):
        if remaining <= length and length:
            f=remaining/length
            return a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f
        remaining-=length
    return tuple(points[-1])


def assess_scene(scene, layout=None):
    """Nominal Excalidraw geometry audit, not browser glyph measurements."""
    elements=[e for e in scene.get('elements',[]) if not e.get('isDeleted')]
    arrows=[e for e in elements if e.get('type')=='arrow']
    edges=[{'id':e['id'],'points':[[e['x']+p[0],e['y']+p[1]] for p in e['points']]} for e in arrows]
    regions=[e for e in elements if e['id'].startswith('region-') and e.get('type')=='rectangle']
    nodes=[e for e in elements if e['id'].startswith('node-') and e.get('type') not in ('text','arrow','line')]
    lines=[e['points'] for e in edges]+frame_lines(regions)
    findings=[]
    # A conservative geometry-only lower bound; typography-aware layout may
    # reserve more. Do not flag side-by-side or nested regions as stacked.
    for upper,lower,gap in region_vertical_gaps(regions):
        if gap < 80-.2:
            findings.append({'code':'region-clearance','regions':[upper['id'],lower['id']],
                             'gap':gap,'minimum':80.})
    if layout is None:
        import importlib.util
        from pathlib import Path
        import sys
        spec=importlib.util.spec_from_file_location('_readable_audit_layout',Path(__file__).with_name('layout.py'))
        layout=importlib.util.module_from_spec(spec); sys.modules[spec.name]=layout; spec.loader.exec_module(layout)
    for pair in layout.geometric_crossing_pairs(edges):
        findings.append({'code':'edge-crossing','edges':pair})
    for pair in parallel_conflicts(edges):
        findings.append({'code':'parallel-clearance',**pair})
    for text in elements:
        if text.get('type')!='text' or not text['id'].startswith(('elabel-','region-label-')): continue
        rect=(text['x'],text['y'],text['width'],text['height'])
        # Header text is intentionally near its own border; only edge labels
        # must clear all region borders. Both must clear relationship lines.
        obstacles=lines if text['id'].startswith('elabel-') else [e['points'] for e in edges]
        hits=[i for i,p in enumerate(obstacles) if any(_hits_rect(a,b,rect,TEXT_CLEARANCE-.2) for a,b in zip(p,p[1:]))]
        if hits: findings.append({'code':'label-clearance','id':text['id'],'text':text.get('text'),'obstacles':hits})
        if text['id'].startswith('elabel-'):
            x,y,w,h=rect; gap=TEXT_CLEARANCE-.2
            near=[n['id'] for n in nodes if x-gap < n['x']+n['width'] and x+w+gap > n['x']
                  and y-gap < n['y']+n['height'] and y+h+gap > n['y']]
            if near: findings.append({'code':'label-node-clearance','id':text['id'],'nodes':near})
    return {'status':'pass' if not findings else 'warning','basis':'native-scene-nominal-geometry',
            'line_clearance':LINE_CLEARANCE,'text_clearance':TEXT_CLEARANCE,
            'bends':sum(max(0,len(e['points'])-2) for e in edges),'findings':findings,
            'limits':['间距为图内单位，观看缩放会改变实际距离；字体包围盒为生成器估算，仍需官方导出目检。']}


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description='检查 Excalidraw 原生几何中的近线、交叉及文字安全间隔；不代替官方渲染。')
    parser.add_argument('scene',type=Path)
    parser.add_argument('-o','--out',type=Path)
    args=parser.parse_args()
    report=assess_scene(json.loads(args.scene.read_text()))
    payload=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.out: args.out.write_text(payload)
    else: print(payload,end='')
    raise SystemExit(0 if report['status']=='pass' else 1)
