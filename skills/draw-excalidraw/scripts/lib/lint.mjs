import { boxesOverlap } from './util.mjs';

export function lintSpec(spec, compiled) {
  const issues=[]; const nodes=spec.nodes||[]; const pos=compiled.positions||{};
  const ids=new Set(nodes.map(n=>n.id));
  for(const e of spec.edges||[]){if(!ids.has(e.from))issues.push({level:'error',code:'EDGE_SOURCE_MISSING',message:`edge source missing: ${e.from}`});if(!ids.has(e.to))issues.push({level:'error',code:'EDGE_TARGET_MISSING',message:`edge target missing: ${e.to}`});if((e.label||'').length>48)issues.push({level:'warn',code:'EDGE_LABEL_LONG',message:`edge label is long: ${e.label}`});}
  for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=pos[nodes[i].id],b=pos[nodes[j].id];if(a&&b&&boxesOverlap(a,b,4))issues.push({level:'warn',code:'NODE_OVERLAP',message:`nodes overlap: ${nodes[i].id} / ${nodes[j].id}`});}
  if(nodes.length>24)issues.push({level:'warn',code:'DENSE_VIEW',message:`${nodes.length} nodes in one view; consider splitting or using ELK`});
  const linked=new Set((spec.edges||[]).flatMap(e=>[e.from,e.to]));for(const n of nodes)if(nodes.length>1&&!linked.has(n.id))issues.push({level:'info',code:'DISCONNECTED_NODE',message:`disconnected node: ${n.id}`});
  if((spec.groups||[]).length>0){const groupIds=new Set((spec.groups||[]).map(g=>g.id));for(const n of nodes)if(n.group&&!groupIds.has(n.group))issues.push({level:'warn',code:'GROUP_MISSING',message:`node ${n.id} references missing group ${n.group}`});}
  return issues;
}
