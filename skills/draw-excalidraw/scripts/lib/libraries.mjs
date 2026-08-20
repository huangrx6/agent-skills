import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { deepClone, ensureDir, exists, fuzzyScore, randomId, readJson, writeJson } from './util.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
export const skillRoot = path.resolve(here, '../..');
const cacheDir = path.join(skillRoot, 'cache');
const catalogFile = path.join(cacheDir, 'excalidraw-libraries.json');
const officialDir = path.join(skillRoot, 'libraries', 'official');
const userDir = path.join(skillRoot, 'libraries', 'user');
const catalogURL = 'https://raw.githubusercontent.com/excalidraw/excalidraw-libraries/main/libraries.json';
const rawBase = 'https://raw.githubusercontent.com/excalidraw/excalidraw-libraries/main/';

export async function syncCatalog() {
  await ensureDir(cacheDir);
  const res = await fetch(catalogURL, {headers:{'user-agent':'draw-excalidraw'}});
  if (!res.ok) throw new Error(`catalog download failed: ${res.status} ${res.statusText}`);
  const data = await res.json();
  await writeJson(catalogFile, data);
  return data.length;
}

export async function getCatalog() {
  if (!await exists(catalogFile)) await syncCatalog();
  return readJson(catalogFile);
}

export async function searchCatalog(q, limit=20) {
  const cat = await getCatalog();
  return cat.map(x=>({x, score:Math.max(fuzzyScore(q,x.name||''), fuzzyScore(q,x.description||''))}))
    .filter(v=>v.score>=0).sort((a,b)=>b.score-a.score).slice(0,limit).map(v=>v.x);
}

export async function installLibrary(idOrName) {
  const cat = await getCatalog();
  const item = cat.find(x=>x.id===idOrName) || (await searchCatalog(idOrName,1))[0];
  if (!item) throw new Error(`library not found: ${idOrName}`);
  await ensureDir(officialDir);
  const res = await fetch(rawBase + item.source, {headers:{'user-agent':'draw-excalidraw'}});
  if (!res.ok) throw new Error(`library download failed: ${res.status} ${res.statusText}`);
  const buf = Buffer.from(await res.arrayBuffer());
  const name = path.basename(item.source).replace(/[^a-zA-Z0-9._-]/g,'_');
  const dest = path.join(officialDir, `${item.id}--${name}`);
  await fs.writeFile(dest, buf);
  return {item, dest};
}

async function walk(dir) {
  if (!await exists(dir)) return [];
  const out=[];
  for (const ent of await fs.readdir(dir,{withFileTypes:true})) {
    const p=path.join(dir,ent.name);
    if(ent.isDirectory()) out.push(...await walk(p));
    else if(ent.name.endsWith('.excalidrawlib')) out.push(p);
  }
  return out;
}

function normalizeItems(doc) {
  const raw = doc.libraryItems || doc.library || [];
  return raw.map((item,i)=>Array.isArray(item) ? {id:`legacy-${i}`,name:null,elements:item} : item).filter(x=>Array.isArray(x.elements));
}

function searchable(item, file) {
  const texts = item.elements.filter(e=>e.type==='text' && e.text).map(e=>e.text).join(' ');
  return [item.name||'', texts, path.basename(file)].join(' ');
}

export async function searchInstalledItems(q, limit=20) {
  const files=[...await walk(officialDir),...await walk(userDir)];
  const matches=[];
  for(const file of files){
    let doc; try{doc=JSON.parse(await fs.readFile(file,'utf8'));}catch{continue;}
    const items=normalizeItems(doc);
    items.forEach((item,index)=>{
      const score=fuzzyScore(q,searchable(item,file));
      if(score>=0) matches.push({file,item,index,score,name:item.name||`${path.basename(file)}#${index+1}`});
    });
  }
  return matches.sort((a,b)=>b.score-a.score).slice(0,limit);
}

function remapObjectIds(obj, idMap, groupMap) {
  if (obj.id && idMap.has(obj.id)) obj.id=idMap.get(obj.id);
  if (Array.isArray(obj.groupIds)) obj.groupIds=obj.groupIds.map(g=>groupMap.get(g)||g);
  if (obj.containerId && idMap.has(obj.containerId)) obj.containerId=idMap.get(obj.containerId);
  if (obj.frameId && idMap.has(obj.frameId)) obj.frameId=idMap.get(obj.frameId);
  if (Array.isArray(obj.boundElements)) obj.boundElements=obj.boundElements.map(b=>({...b,id:idMap.get(b.id)||b.id}));
  if (obj.startBinding?.elementId && idMap.has(obj.startBinding.elementId)) obj.startBinding.elementId=idMap.get(obj.startBinding.elementId);
  if (obj.endBinding?.elementId && idMap.has(obj.endBinding.elementId)) obj.endBinding.elementId=idMap.get(obj.endBinding.elementId);
}

export async function instantiateLibraryItem(query, x, y, size=42) {
  const hit=(await searchInstalledItems(query,1))[0];
  if(!hit) return null;
  const elements=deepClone(hit.item.elements).filter(e=>e.type!=='image');
  if(!elements.length) return null;
  const minX=Math.min(...elements.map(e=>e.x||0)), minY=Math.min(...elements.map(e=>e.y||0));
  const maxX=Math.max(...elements.map(e=>(e.x||0)+(e.width||0))), maxY=Math.max(...elements.map(e=>(e.y||0)+(e.height||0)));
  const w=Math.max(1,maxX-minX), h=Math.max(1,maxY-minY), scale=size/Math.max(w,h);
  const idMap=new Map(elements.map(e=>[e.id,randomId('lib')]));
  const groups=[...new Set(elements.flatMap(e=>e.groupIds||[]))];
  const groupMap=new Map(groups.map(g=>[g,randomId('grp')]));
  for(const e of elements){
    remapObjectIds(e,idMap,groupMap);
    e.x=x+(e.x-minX)*scale; e.y=y+(e.y-minY)*scale;
    if(Number.isFinite(e.width)) e.width*=scale;
    if(Number.isFinite(e.height)) e.height*=scale;
    if(Array.isArray(e.points)) e.points=e.points.map(([px,py])=>[px*scale,py*scale]);
    if(Number.isFinite(e.fontSize)) e.fontSize=Math.max(8,e.fontSize*scale);
    e.updated=Date.now(); e.version=1; e.versionNonce=Math.floor(Math.random()*2e9)+1;
  }
  return {elements, name:hit.name, source:hit.file};
}
