import { randomId, randomInt, now, measureText, wrapText, sha1 } from './util.mjs';

function common(type,x,y,width,height,opts={}) {
  return {
    id: opts.id || randomId(type.slice(0,3)), type, x, y, width, height, angle:0,
    strokeColor: opts.strokeColor || '#343a40', backgroundColor: opts.backgroundColor ?? 'transparent',
    fillStyle: opts.fillStyle || 'solid', strokeWidth: opts.strokeWidth ?? 2, strokeStyle: opts.strokeStyle || 'solid',
    roughness: opts.roughness ?? 1, opacity: opts.opacity ?? 100, groupIds: opts.groupIds || [], frameId:null,
    roundness: opts.roundness ?? null, seed: randomInt(), version:1, versionNonce:randomInt(), isDeleted:false,
    boundElements: opts.boundElements || [], updated:now(), link:opts.link||null, locked:opts.locked||false
  };
}

export function shape(type,x,y,w,h,opts={}) {
  const roundness = type==='rectangle' ? {type:3} : type==='ellipse' ? {type:2} : null;
  return common(type,x,y,w,h,{...opts,roundness:opts.roundness??roundness});
}

export function textElement(text,x,y,opts={}) {
  const fontSize=opts.fontSize||16, lineHeight=opts.lineHeight||1.25;
  const wrapped=opts.maxUnits?wrapText(text,opts.maxUnits):String(text);
  const m=measureText(wrapped,fontSize,lineHeight);
  const el=common('text',x,y,Math.ceil(opts.width||m.width),Math.ceil(opts.height||m.height),{
    ...opts, backgroundColor:'transparent', fillStyle:'solid', strokeWidth:1, roughness:0, roundness:null, boundElements:[]
  });
  return Object.assign(el,{text:wrapped,rawText:wrapped,originalText:wrapped,fontSize,fontFamily:opts.fontFamily||2,textAlign:opts.textAlign||'left',verticalAlign:opts.verticalAlign||'top',containerId:opts.containerId||null,autoResize:true,lineHeight,hasTextLink:false});
}

export function arrowElement(points,opts={}) {
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const minX=Math.min(...xs),minY=Math.min(...ys),maxX=Math.max(...xs),maxY=Math.max(...ys);
  const rel=points.map(([x,y])=>[x-minX,y-minY]);
  const el=common('arrow',minX,minY,Math.max(1,maxX-minX),Math.max(1,maxY-minY),{
    ...opts, backgroundColor:'transparent', fillStyle:'solid', roundness:opts.roundness??{type:2}, boundElements:opts.boundElements||[]
  });
  return Object.assign(el,{points:rel,lastCommittedPoint:null,startBinding:opts.startBinding||null,endBinding:opts.endBinding||null,startArrowhead:opts.startArrowhead??null,endArrowhead:opts.endArrowhead===undefined?'arrow':opts.endArrowhead,elbowed:false,moveMidPointsWithElement:false});
}

export function lineElement(points,opts={}) {
  const a=arrowElement(points,{...opts,endArrowhead:null}); a.type='line'; return a;
}

export function imageElement(data,x,y,w,h,opts={}) {
  const el=common('image',x,y,w,h,{...opts,backgroundColor:'transparent',strokeColor:'transparent',strokeWidth:0,roughness:0,boundElements:[]});
  return Object.assign(el,{status:'saved',fileId:data.fileId,scale:[1,1],crop:null});
}

export function binaryFile(data) {
  return {mimeType:'image/svg+xml',id:data.fileId,dataURL:data.dataURL,created:now(),lastRetrieved:now()};
}
