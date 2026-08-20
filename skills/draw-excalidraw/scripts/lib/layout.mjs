import { clamp } from './util.mjs';

function manual(nodes) {
  return Object.fromEntries(nodes.map((n,i)=>[n.id,{x:Number.isFinite(n.x)?n.x:(i%4)*260,y:Number.isFinite(n.y)?n.y:Math.floor(i/4)*160,width:n._size.width,height:n._size.height}]));
}

function simpleLayered(nodes, edges, direction='LR') {
  const indeg=new Map(nodes.map(n=>[n.id,0]));
  for(const e of edges) if(indeg.has(e.to)) indeg.set(e.to, indeg.get(e.to)+1);
  const q=nodes.filter(n=>indeg.get(n.id)===0).map(n=>n.id);
  const rank=new Map(nodes.map(n=>[n.id,0]));
  while(q.length){const id=q.shift(); for(const e of edges.filter(e=>e.from===id)){rank.set(e.to,Math.max(rank.get(e.to)||0,(rank.get(id)||0)+1)); indeg.set(e.to,(indeg.get(e.to)||0)-1); if(indeg.get(e.to)===0)q.push(e.to);}}
  const by=new Map(); for(const n of nodes){const r=rank.get(n.id)||0; if(!by.has(r))by.set(r,[]);by.get(r).push(n);}
  const out={}; const rankSep=260,nodeSep=130;
  for(const [r,arr] of [...by.entries()].sort((a,b)=>a[0]-b[0])) arr.forEach((n,i)=>{
    const primary=r*rankSep, secondary=i*nodeSep;
    out[n.id]=direction==='TB'||direction==='BT'?{x:secondary,y:primary,width:n._size.width,height:n._size.height}:{x:primary,y:secondary,width:n._size.width,height:n._size.height};
  });
  if(direction==='RL'){const max=Math.max(...Object.values(out).map(p=>p.x)); for(const p of Object.values(out))p.x=max-p.x;}
  if(direction==='BT'){const max=Math.max(...Object.values(out).map(p=>p.y)); for(const p of Object.values(out))p.y=max-p.y;}
  return out;
}

async function dagreLayout(nodes, edges, opts) {
  const dagre = await import('@dagrejs/dagre');
  const g = new dagre.graphlib.Graph();
  g.setGraph({rankdir:opts.direction||'LR', nodesep:opts.nodeSeparation||70, ranksep:opts.rankSeparation||120, marginx:30, marginy:30});
  g.setDefaultEdgeLabel(()=>({}));
  nodes.forEach(n=>g.setNode(n.id,{width:n._size.width,height:n._size.height}));
  edges.forEach((e,i)=>{if(g.hasNode(e.from)&&g.hasNode(e.to))g.setEdge(e.from,e.to,{id:e.id||`e${i}`});});
  dagre.layout(g);
  return Object.fromEntries(nodes.map(n=>{const p=g.node(n.id);return[n.id,{x:p.x-n._size.width/2,y:p.y-n._size.height/2,width:n._size.width,height:n._size.height}]}));
}

async function elkLayout(nodes, edges, opts) {
  const mod=await import('elkjs/lib/elk.bundled.js'); const ELK=mod.default||mod; const elk=new ELK();
  const direction=opts.direction||'RIGHT';
  const map={LR:'RIGHT',RL:'LEFT',TB:'DOWN',BT:'UP'};
  const graph={id:'root',layoutOptions:{'elk.algorithm':'layered','elk.direction':map[direction]||direction,'elk.spacing.nodeNode':String(opts.nodeSeparation||70),'elk.layered.spacing.nodeNodeBetweenLayers':String(opts.rankSeparation||120),'elk.edgeRouting':'ORTHOGONAL'},children:nodes.map(n=>({id:n.id,width:n._size.width,height:n._size.height})),edges:edges.filter(e=>nodes.some(n=>n.id===e.from)&&nodes.some(n=>n.id===e.to)).map((e,i)=>({id:e.id||`e${i}`,sources:[e.from],targets:[e.to]}))};
  const res=await elk.layout(graph);
  return Object.fromEntries((res.children||[]).map(n=>[n.id,{x:n.x||0,y:n.y||0,width:n.width,height:n.height}]));
}

export async function layoutNodes(spec, nodes, edges) {
  const engine=spec.layout?.engine||'auto';
  if(engine==='manual') return manual(nodes);
  const opts={direction:spec.direction||((spec.type==='flowchart'||spec.type==='state')?'TB':'LR'),nodeSeparation:spec.layout?.nodeSeparation,rankSeparation:spec.layout?.rankSeparation};
  try {
    if(engine==='elk'||(engine==='auto'&&(nodes.length>18||(spec.groups||[]).length>3))) return await elkLayout(nodes,edges,opts);
    if(engine==='dagre'||engine==='auto') return await dagreLayout(nodes,edges,opts);
  } catch (e) {
    if(process.env.DRAW_EXCALIDRAW_DEBUG) console.error(`layout fallback: ${e.message}`);
  }
  return simpleLayered(nodes,edges,opts.direction);
}

export function layoutMindmap(tree, direction='LR') {
  const out={}; let cursor=0;
  const walk=(node,depth=0)=>{const children=node.children||[]; const start=cursor; if(!children.length)cursor+=110; else children.forEach(c=>walk(c,depth+1)); const center=children.length?(start+cursor-110)/2:cursor-110; out[node.id||node.label]={x:depth*260,y:center,width:190,height:72,node};};
  walk(tree,0); return out;
}
