import fs from 'node:fs/promises';
import { bboxUnion } from './util.mjs';

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
export async function writePreview(scene,file){
  const els=scene.elements.filter(e=>!e.isDeleted); const boxes=els.filter(e=>Number.isFinite(e.x)&&Number.isFinite(e.y)&&Number.isFinite(e.width)&&Number.isFinite(e.height)).map(e=>({x:e.x,y:e.y,width:e.width,height:e.height}));const b=bboxUnion(boxes),pad=40; const vb=[b.x-pad,b.y-pad,Math.max(320,b.width+pad*2),Math.max(200,b.height+pad*2)];
  const out=[`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb.join(' ')}" width="${Math.ceil(vb[2])}" height="${Math.ceil(vb[3])}">`,`<rect x="${vb[0]}" y="${vb[1]}" width="${vb[2]}" height="${vb[3]}" fill="${scene.appState?.viewBackgroundColor||'#fff'}"/>`,`<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#495057"/></marker></defs>`];
  for(const e of els){
    if(e.type==='rectangle')out.push(`<rect x="${e.x}" y="${e.y}" width="${e.width}" height="${e.height}" rx="12" fill="${e.backgroundColor}" fill-opacity="${(e.opacity??100)/100}" stroke="${e.strokeColor}" stroke-width="${e.strokeWidth||1}" stroke-dasharray="${e.strokeStyle==='dashed'?'8 6':'none'}"/>`);
    else if(e.type==='ellipse')out.push(`<ellipse cx="${e.x+e.width/2}" cy="${e.y+e.height/2}" rx="${e.width/2}" ry="${e.height/2}" fill="${e.backgroundColor}" stroke="${e.strokeColor}" stroke-width="${e.strokeWidth||1}"/>`);
    else if(e.type==='diamond'){const x=e.x,y=e.y,w=e.width,h=e.height;out.push(`<polygon points="${x+w/2},${y} ${x+w},${y+h/2} ${x+w/2},${y+h} ${x},${y+h/2}" fill="${e.backgroundColor}" stroke="${e.strokeColor}" stroke-width="${e.strokeWidth||1}"/>`);}
    else if(e.type==='text'){const lines=String(e.text||'').split('\n');lines.forEach((ln,i)=>out.push(`<text x="${e.x}" y="${e.y+(i+1)*(e.fontSize||16)*1.15}" font-family="Arial, sans-serif" font-size="${e.fontSize||16}" fill="${e.strokeColor}">${esc(ln)}</text>`));}
    else if(e.type==='arrow'||e.type==='line'){const pts=e.points.map(([x,y])=>[x+e.x,y+e.y]);const d=pts.map((p,i)=>(i?'L':'M')+p.join(',')).join(' ');out.push(`<path d="${d}" fill="none" stroke="${e.strokeColor}" stroke-width="${e.strokeWidth||1}" stroke-dasharray="${e.strokeStyle==='dashed'?'8 6':'none'}" ${e.type==='arrow'&&e.endArrowhead?`marker-end="url(#arrow)"`:''}/>`);}
    else if(e.type==='image'&&e.fileId&&scene.files?.[e.fileId]) out.push(`<image x="${e.x}" y="${e.y}" width="${e.width}" height="${e.height}" href="${scene.files[e.fileId].dataURL}"/>`);
  }
  out.push('</svg>'); await fs.writeFile(file,out.join('\n'),'utf8');
}
