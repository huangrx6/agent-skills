import path from 'node:path';
import { loadTheme, styleForKind } from './theme.mjs';
import { parseIcon, iconSvgData } from './icons.mjs';
import { instantiateLibraryItem } from './libraries.mjs';
import { layoutNodes, layoutMindmap } from './layout.mjs';
import { shape, textElement, arrowElement, lineElement, imageElement, binaryFile } from './elements.mjs';
import { bboxUnion, measureText, randomId, wrapText } from './util.mjs';

const iconArea=54, nodePad=18;

function nodeSize(n, theme, type) {
  if(Number.isFinite(n.width)&&Number.isFinite(n.height)) return {width:n.width,height:n.height};
  if(type==='er') {
    const fields=n.fields||[]; const max=Math.max(measureText(n.label,theme.nodeFontSize).width,...fields.map(f=>measureText(f,theme.detailFontSize).width),160);
    return {width:Math.min(360,Math.max(210,max+40)),height:62+fields.length*(theme.detailFontSize*1.35)+20};
  }
  const title=wrapText(n.label||n.id,18); const tm=measureText(title,theme.nodeFontSize);
  const detail=n.detail?measureText(wrapText(n.detail,24),theme.detailFontSize):{width:0,height:0};
  return {width:Math.max(190,Math.min(300,iconArea+tm.width+nodePad*2,detail.width+nodePad*2)),height:Math.max(76,tm.height+detail.height+nodePad*2+(detail.height?8:0))};
}

function edgeStyle(e, theme) {
  const kind=e.kind||'call';
  if(kind==='async') return {strokeStyle:'dashed',strokeColor:'#e67700'};
  if(kind==='data') return {strokeStyle:'solid',strokeColor:'#7048e8'};
  if(kind==='return') return {strokeStyle:'dashed',strokeColor:'#68717a'};
  if(kind==='conditional') return {strokeStyle:'dashed',strokeColor:'#495057'};
  return {strokeStyle:e.style||'solid',strokeColor:theme.stroke};
}

function anchors(a,b,direction='LR') {
  const ac={x:a.x+a.width/2,y:a.y+a.height/2},bc={x:b.x+b.width/2,y:b.y+b.height/2};
  const horizontal=Math.abs(bc.x-ac.x)>=Math.abs(bc.y-ac.y);
  if(horizontal){const s=bc.x>=ac.x?{x:a.x+a.width,y:ac.y}:{x:a.x,y:ac.y}; const t=bc.x>=ac.x?{x:b.x,y:bc.y}:{x:b.x+b.width,y:bc.y}; return[s,t];}
  const s=bc.y>=ac.y?{x:ac.x,y:a.y+a.height}:{x:ac.x,y:a.y}; const t=bc.y>=ac.y?{x:bc.x,y:b.y}:{x:bc.x,y:b.y+b.height}; return[s,t];
}

function orthogonalPoints(s,t) {
  if(Math.abs(t.x-s.x)>=Math.abs(t.y-s.y)){const m=(s.x+t.x)/2;return [[s.x,s.y],[m,s.y],[m,t.y],[t.x,t.y]];}
  const m=(s.y+t.y)/2;return [[s.x,s.y],[s.x,m],[t.x,m],[t.x,t.y]];
}

async function compileGraph(spec,theme) {
  const files={}, elements=[], nodeElements=new Map(), positions={};
  const nodes=(spec.nodes||[]).map(n=>({...n,_size:nodeSize(n,theme,spec.type)}));
  const pos=await layoutNodes(spec,nodes,spec.edges||[]);
  const titleOffset=spec.title?130:30;
  for(const n of nodes){const p=pos[n.id]||{x:0,y:0,width:n._size.width,height:n._size.height};positions[n.id]={...p,y:p.y+titleOffset};}

  // groups first as soft background boundaries
  const groups=spec.groups||[];
  for(const g of groups){
    const members=nodes.filter(n=>n.group===g.id).map(n=>positions[n.id]).filter(Boolean);
    if(!members.length)continue;
    const b=bboxUnion(members), pad=34, top=42;
    const ge=shape('rectangle',b.x-pad,b.y-top,b.width+pad*2,b.height+top+pad,{strokeColor:'#adb5bd',backgroundColor:'#f8f9fa',strokeStyle:'dashed',strokeWidth:1,roughness:0,opacity:55,locked:true});
    elements.push(ge,textElement(g.label,b.x-pad+14,b.y-top+10,{fontSize:18,fontFamily:theme.fontFamily,strokeColor:'#495057'}));
  }

  if(spec.title) elements.push(textElement(spec.title,20,16,{fontSize:theme.titleFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text}));
  if(spec.subtitle) elements.push(textElement(spec.subtitle,20,54,{fontSize:14,fontFamily:theme.fontFamily,strokeColor:theme.muted}));

  for(const n of nodes){
    const p=positions[n.id], style=styleForKind(theme,n.kind||'default'), groupId=randomId('grp');
    const type=n.shape||(n.kind==='decision'?'diamond':'rectangle');
    const sh=shape(type,p.x,p.y,p.width,p.height,{id:`node_${n.id}`,strokeColor:style.strokeColor,backgroundColor:style.backgroundColor,fillStyle:'solid',strokeWidth:theme.strokeWidth,roughness:theme.roughness,groupIds:[groupId],boundElements:[]});
    elements.push(sh); nodeElements.set(n.id,sh);

    if(spec.type==='er'){
      const explicitIcon=n.icon?parseIcon(n.icon,style.icon):{provider:'none',name:''};
      let titleX=p.x+16;
      if(explicitIcon.provider!=='none'&&explicitIcon.provider!=='library'){
        const data=await iconSvgData(explicitIcon.provider,explicitIcon.name,style.strokeColor).catch(()=>null);
        if(data){files[data.fileId]=binaryFile(data);elements.push(imageElement(data,p.x+14,p.y+13,24,24,{groupIds:[groupId]}));titleX=p.x+46;}
      }
      elements.push(textElement(n.label||n.id,titleX,p.y+12,{fontSize:theme.nodeFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text,width:p.width-(titleX-p.x)-16,groupIds:[groupId]}));
      elements.push(lineElement([[p.x+12,p.y+44],[p.x+p.width-12,p.y+44]],{strokeColor:style.strokeColor,strokeWidth:1,roughness:0,groupIds:[groupId]}));
      const fieldText=(n.fields||[]).join('\n');
      if(fieldText)elements.push(textElement(fieldText,p.x+16,p.y+54,{fontSize:theme.detailFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text,width:p.width-32,groupIds:[groupId]}));
      continue;
    }

    let textX=p.x+nodePad, textWidth=p.width-nodePad*2;
    const implicitNoIcon = (type==='diamond'||type==='ellipse') && !n.icon;
    const icon=implicitNoIcon?{provider:'none',name:''}:parseIcon(n.icon,style.icon);
    if(icon.provider==='library'){
      const lib=await instantiateLibraryItem(icon.name,p.x+14,p.y+(p.height-40)/2,40).catch(()=>null);
      if(lib){lib.elements.forEach(e=>{e.groupIds=[...(e.groupIds||[]),groupId];elements.push(e);}); textX=p.x+iconArea; textWidth=p.width-iconArea-nodePad;}
      else {
        const data=await iconSvgData('lucide',style.icon,style.strokeColor).catch(()=>null);
        if(data){files[data.fileId]=binaryFile(data);elements.push(imageElement(data,p.x+16,p.y+(p.height-34)/2,34,34,{groupIds:[groupId]}));textX=p.x+iconArea;textWidth=p.width-iconArea-nodePad;}
      }
    } else if(icon.provider!=='none') {
      const data=await iconSvgData(icon.provider,icon.name,style.strokeColor).catch(()=>null);
      if(data){files[data.fileId]=binaryFile(data);elements.push(imageElement(data,p.x+16,p.y+(p.height-34)/2,34,34,{groupIds:[groupId]}));textX=p.x+iconArea;textWidth=p.width-iconArea-nodePad;}
    }
    const title=wrapText(n.label||n.id,Math.max(10,textWidth/theme.nodeFontSize/0.6));
    const tm=measureText(title,theme.nodeFontSize); const detail=n.detail?wrapText(n.detail,Math.max(12,textWidth/theme.detailFontSize/0.6)):''; const dm=detail?measureText(detail,theme.detailFontSize):{height:0};
    const total=tm.height+(detail?dm.height+7:0); let ty=p.y+(p.height-total)/2;
    elements.push(textElement(title,textX,ty,{fontSize:theme.nodeFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text,width:textWidth,groupIds:[groupId]}));
    if(detail) elements.push(textElement(detail,textX,ty+tm.height+7,{fontSize:theme.detailFontSize,fontFamily:theme.fontFamily,strokeColor:theme.muted,width:textWidth,groupIds:[groupId]}));
  }

  // arrows after nodes, labels after arrows
  for(let i=0;i<(spec.edges||[]).length;i++){
    const e=spec.edges[i], a=positions[e.from], b=positions[e.to]; if(!a||!b)continue;
    const [s,t]=anchors(a,b,spec.direction); const pts=orthogonalPoints(s,t); const st=edgeStyle(e,theme); const id=e.id||`edge_${e.from}_${e.to}_${i}`;
    const ar=arrowElement(pts,{id,strokeColor:st.strokeColor,strokeStyle:st.strokeStyle,strokeWidth:2,roughness:0.7,startBinding:{elementId:`node_${e.from}`,focus:0,gap:4},endBinding:{elementId:`node_${e.to}`,focus:0,gap:4},endArrowhead:'arrow',boundElements:[]});
    elements.push(ar);
    nodeElements.get(e.from)?.boundElements.push({id:ar.id,type:'arrow'}); nodeElements.get(e.to)?.boundElements.push({id:ar.id,type:'arrow'});
    if(e.label){
      let best=null;
      for(let si=0;si<pts.length-1;si++){const a1=pts[si],b1=pts[si+1],len=Math.hypot(b1[0]-a1[0],b1[1]-a1[1]);if(!best||len>best.len)best={a:a1,b:b1,len};}
      const mx=(best.a[0]+best.b[0])/2,my=(best.a[1]+best.b[1])/2,horizontal=Math.abs(best.b[0]-best.a[0])>=Math.abs(best.b[1]-best.a[1]);
      const lm=measureText(e.label,theme.edgeFontSize);
      const lx=horizontal?mx-lm.width/2:mx+8, ly=horizontal?my-lm.height-7:my-lm.height/2;
      const label=textElement(e.label,lx,ly,{fontSize:theme.edgeFontSize,fontFamily:theme.fontFamily,strokeColor:st.strokeColor,containerId:ar.id,textAlign:'center',verticalAlign:'middle'}); ar.boundElements.push({id:label.id,type:'text'}); elements.push(label);
    }
  }
  return {elements,files,positions};
}

async function compileSequence(spec,theme){
  const elements=[],files={},participants=spec.participants||[],messages=spec.messages||[]; const margin=70,laneW=220,top=100,headerW=170,headerH=64,row=64;
  if(spec.title)elements.push(textElement(spec.title,20,18,{fontSize:theme.titleFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text}));
  const xmap={};
  for(let i=0;i<participants.length;i++){
    const p=participants[i],x=margin+i*laneW;xmap[p.id]=x+headerW/2;const style=styleForKind(theme,p.kind||'default'),gid=randomId('grp');
    elements.push(shape('rectangle',x,top,headerW,headerH,{strokeColor:style.strokeColor,backgroundColor:style.backgroundColor,groupIds:[gid]}));
    const icon=parseIcon(p.icon,style.icon); const data=icon.provider!=='library'&&icon.provider!=='none'?await iconSvgData(icon.provider,icon.name,style.strokeColor).catch(()=>null):null;
    if(data){files[data.fileId]=binaryFile(data);elements.push(imageElement(data,x+12,top+15,32,32,{groupIds:[gid]}));}
    elements.push(textElement(p.label,x+(data?52:16),top+20,{fontSize:theme.nodeFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text,width:headerW-(data?60:28),groupIds:[gid]}));
    const bottom=top+headerH+Math.max(260,messages.length*row+70);elements.push(lineElement([[x+headerW/2,top+headerH],[x+headerW/2,bottom]],{strokeColor:'#adb5bd',strokeStyle:'dashed',strokeWidth:1,roughness:0}));
  }
  messages.forEach((m,i)=>{const y=top+headerH+50+i*row,from=xmap[m.from],to=xmap[m.to];if(from==null||to==null)return;const ret=m.kind==='return';const st=ret?{strokeStyle:'dashed',strokeColor:'#68717a'}:edgeStyle(m,theme);const ar=arrowElement([[from,y],[to,y]],{strokeColor:st.strokeColor,strokeStyle:st.strokeStyle,roughness:.7,endArrowhead:'arrow'});elements.push(ar);if(m.label)elements.push(textElement(m.label,Math.min(from,to)+Math.abs(to-from)/2-60,y-24,{fontSize:theme.edgeFontSize,fontFamily:theme.fontFamily,strokeColor:st.strokeColor,width:120,textAlign:'center'}));});
  return {elements,files,positions:{}};
}

async function compileMindmap(spec,theme){
  const tree=spec.tree; if(!tree) throw new Error('mindmap requires tree'); const layout=layoutMindmap(tree,spec.direction||'LR'),elements=[],files={};
  if(spec.title)elements.push(textElement(spec.title,20,16,{fontSize:theme.titleFontSize,fontFamily:theme.fontFamily,strokeColor:theme.text}));
  const offsetY=spec.title?70:20, nodeMap=new Map();
  for(const [id,p] of Object.entries(layout)){const depth=Math.round(p.x/260),kind=depth===0?'security':depth===1?'service':'default',style=styleForKind(theme,kind);const sh=shape('rectangle',p.x+20,p.y+offsetY,p.width,p.height,{id:`node_${id}`,backgroundColor:style.backgroundColor,strokeColor:style.strokeColor});elements.push(sh,textElement(p.node.label||id,p.x+36,p.y+offsetY+24,{fontSize:depth===0?19:16,fontFamily:theme.fontFamily,strokeColor:theme.text,width:p.width-32}));nodeMap.set(id,{...p,x:p.x+20,y:p.y+offsetY,el:sh});}
  const walk=(n)=>{for(const c of n.children||[]){const a=nodeMap.get(n.id||n.label),b=nodeMap.get(c.id||c.label);if(a&&b){const [s,t]=anchors(a,b,'LR');const ar=arrowElement([[s.x,s.y],[t.x,t.y]],{strokeColor:'#868e96',strokeWidth:1,roughness:.8});elements.push(ar);a.el.boundElements.push({id:ar.id,type:'arrow'});b.el.boundElements.push({id:ar.id,type:'arrow'});}walk(c);}};walk(tree);
  return {elements,files,positions:layout};
}

export async function compileSpec(spec){
  const theme=await loadTheme(spec.theme||'technical'); let result;
  if(spec.type==='sequence')result=await compileSequence(spec,theme); else if(spec.type==='mindmap')result=await compileMindmap(spec,theme); else result=await compileGraph(spec,theme);
  return {scene:{type:'excalidraw',version:2,source:'draw-excalidraw',elements:result.elements,appState:{gridSize:null,viewBackgroundColor:theme.canvas,currentItemFontFamily:theme.fontFamily},files:result.files},positions:result.positions,theme};
}
