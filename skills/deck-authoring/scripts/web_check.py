#!/usr/bin/env python3
"""Measure compiled free-composition HTML in one real Chrome session.

Hard errors: failed readiness/resources, text outside the slide or clipped by an
ancestor, and moving content after a completed seek. Text-to-text intersections
require visual review; typography heuristics are advisories, not aesthetic verdicts. Geometry
is measured from DOM Range line boxes, never estimated from character counts.

Usage: python3 web_check.py deck.html --json layout-report.json
Review findings exit 2; hard failures exit 1. Use --strict to block on all
advisories too. Intentional
local exceptions use data-web-check-allow="text-overlap" and a nonempty
data-web-check-reason. Hard errors cannot be exempted. Every applied review
exception remains visible in the report.
This checks completed export frames; it is not a live playback/motion audit.
Reports identify the starting HTML bytes by SHA256 and UTC check times. Input
changes or removal during inspection invalidate the result with a hard error.

Opt-in .deck-page layouts also enforce header/body/footer capacity using actual
body geometry and its authored CSS padding. There is no default block-count
limit. A positive integer data-max-blocks sets a project-specific budget;
exceeding that explicit budget needs review. Primary body type has a 24px
recommendation for default screen viewing, or 28px for data-viewing="room".
Text size, authored scaling, caption-only content and unmarked semantic units
are non-blocking advisories. They remain subject to all geometric checks.
Default small-type advisories distinguish auxiliary roles in a valid .deck-page:
captions/kickers use 16px and footers use 14px. Other text keeps the 24px advisory. An
explicit --min-font overrides these advisory thresholds for every role, while
the body viewing-context recommendation remains an independent advisory.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent

_browser_spec = importlib.util.spec_from_file_location("_deck_browser", HERE / "browser.py")
if _browser_spec is None or _browser_spec.loader is None:
    raise RuntimeError(f"加载不了 browser.py：{HERE / 'browser.py'}")
browser = importlib.util.module_from_spec(_browser_spec)
_browser_spec.loader.exec_module(browser)


def _connect():
    for name in ("websockets.asyncio.client", "websockets"):
        try:
            module = __import__(name, fromlist=["connect"])
        except ImportError:
            continue
        return module.connect
    raise RuntimeError("websockets is required; install requirements.txt")


# Keep this collector independent of spec/data-m and of particular visual styles.
COLLECT_JS = r"""
window.__webCheckCollect = function(slide, options) {
  const round = n => Math.round(n * 100) / 100;
  const box = r => ({x:round(r.left),y:round(r.top),w:round(r.width),h:round(r.height)});
  const issues=[], exemptions=[], runs=[], signatures=[];
  const bounds=slide.getBoundingClientRect();
  const label = el => {
    if (el.id) return '#' + el.id;
    const parts=[];
    for(let cur=el;cur && cur!==slide;cur=cur.parentElement){
      const siblings=cur.parentElement ? Array.from(cur.parentElement.children).filter(x=>x.tagName===cur.tagName) : [];
      parts.unshift(cur.tagName.toLowerCase() + (siblings.length>1 ? ':nth-of-type('+(siblings.indexOf(cur)+1)+')' : ''));
    }
    return '[data-slide="'+slide.dataset.slide+'"] > '+parts.join(' > ');
  };
  const visible = el => {
    for(let cur=el;cur;cur=cur.parentElement){
      const cs=getComputedStyle(cur);
      if(cs.display==='none'||cs.visibility==='hidden'||cs.visibility==='collapse'||Number(cs.opacity)===0) return false;
      if(cur===slide) break;
    }
    return true;
  };
  function exemption(el, code) {
    for(let cur=el;cur && cur!==slide;cur=cur.parentElement){
      if((cur.getAttribute('data-web-check-allow')||'').split(/\s+/).includes(code)){
        const reason=(cur.getAttribute('data-web-check-reason')||'').trim();
        if(reason) return {element:label(cur),reason};
      }
    }
    return null;
  }
  function add(code,severity,message,el,details={},other=null){
    const issue={code,severity,message,element:label(el),...details};
    if(['text-overlap','text-mask','svg-fill-overridden','text-occluded','body-block-budget','media-clipped','media-occluded','body-type-too-small'].includes(code)) issue.requiresReview=true;
    const exemptible=['text-overlap','text-mask','svg-fill-overridden','text-occluded','small-text','media-clipped','media-occluded','body-type-too-small'].includes(code);
    const allowed=severity==='warning'&&exemptible&&(exemption(el,code)||(other && exemption(other,code)));
    if(allowed) exemptions.push({...issue,...allowed}); else issues.push(issue);
  }
  function semantic(el){
    if(el instanceof SVGElement) return el.closest('text')||el;
    while(el.parentElement && el.parentElement!==slide && /^(inline|contents)$/.test(getComputedStyle(el).display)) el=el.parentElement;
    return el;
  }
  const walker=document.createTreeWalker(slide,NodeFilter.SHOW_TEXT);
  let node;
  while((node=walker.nextNode())){
    const el=node.parentElement;
    if(!node.nodeValue.trim() || el.closest('script,style,defs,title,desc') || !visible(el)) continue;
    const range=document.createRange(); range.selectNodeContents(node);
    const rects=Array.from(range.getClientRects()).filter(r=>r.width>.1&&r.height>.1);
    if(!rects.length) continue;
    const css=getComputedStyle(el), group=semantic(el), fullText=node.nodeValue.trim().replace(/\s+/g,' '), text=fullText.slice(0,100);
    const fontSize=parseFloat(css.fontSize), run={el,group,text,fontSize,characterCount:Array.from(fullText).length,rects}; runs.push(run);
    signatures.push({element:label(el),text,rects:rects.map(box)});
    if(/待配图|待回填|待生成图|占位图|图片占位/.test(fullText))
      add('placeholder-label','error','Visible placeholder copy inside an image slot; keep the slot blank and move the note outside the image',el,{text});
    const over=rects.map(r=>({left:Math.max(0,bounds.left-r.left),top:Math.max(0,bounds.top-r.top),right:Math.max(0,r.right-bounds.right),bottom:Math.max(0,r.bottom-bounds.bottom)}));
    const excess=Object.fromEntries(['left','top','right','bottom'].map(k=>[k,round(Math.max(...over.map(r=>r[k])))]));
    if(Object.values(excess).some(v=>v>options.tolerance)) add('text-outside-slide','error','Text extends outside the slide',el,{text,excess,rects:rects.map(box)});
    for(let cur=el;cur && cur!==slide;cur=cur.parentElement){
      const cs=getComputedStyle(cur), clipX=/^(hidden|clip|auto|scroll)$/.test(cs.overflowX), clipY=/^(hidden|clip|auto|scroll)$/.test(cs.overflowY);
      if(!clipX&&!clipY) continue;
      const r=cur.getBoundingClientRect(), svg=cur instanceof SVGElement;
      // Transform-adjust border/client dimensions to the rendered coordinate system.
      const sx=svg||!cur.offsetWidth ? 1 : r.width/cur.offsetWidth, sy=svg||!cur.offsetHeight ? 1 : r.height/cur.offsetHeight;
      const left=r.left+(svg?0:cur.clientLeft*sx), top=r.top+(svg?0:cur.clientTop*sy);
      const right=left+(svg?r.width:cur.clientWidth*sx), bottom=top+(svg?r.height:cur.clientHeight*sy);
      const clipped=rects.filter(t=>(clipX&&(t.left<left-options.tolerance||t.right>right+options.tolerance))||(clipY&&(t.top<top-options.tolerance||t.bottom>bottom+options.tolerance)));
      if(clipped.length){add('text-clipped','error','Text is clipped by an overflow container',el,{text,clippedBy:label(cur),clip:box({left,top,width:right-left,height:bottom-top}),rects:clipped.map(box)});break;}
    }
    if(!rects.every(r=>r.width===0)) {
      for(let cur=el;cur&&cur!==slide;cur=cur.parentElement){
        const cs=getComputedStyle(cur);
        if(cs.clipPath!=='none'||cs.maskImage!=='none'){
          add('text-mask','warning','Text has a custom clipping path/mask; visually verify glyph visibility',el,{text,maskedBy:label(cur)});break;
        }
      }
    }
  }
  // Optional capacity contract. Legacy arbitrary HTML keeps its existing rules;
  // this never chooses a layout, shrinks text or splits semantic content for it.
  let layoutBudget=null;
  let typeRegions=null;
  const pageRoots=Array.from(slide.querySelectorAll('.deck-page'));
  if(!pageRoots.length){
    // 自定义页面根：容量/越界契约无法生效。给出明确提示，避免"检查通过"被误读。
    add('no-capacity-contract','warning',
      'This slide has no .deck-page, so capacity, footer-intrusion and region checks did not run',
      slide,{hint:'wrap the page in <div class="deck-page"> or verify page capacity by screenshot'});
  }
  if(pageRoots.length){
    const page=pageRoots[0];
    const viewing=page.getAttribute('data-viewing')??'screen';
    const minBodyFontRecommended=viewing==='screen'?24:viewing==='room'?28:null;
    if(minBodyFontRecommended===null) add('layout-contract-invalid','error',
      'data-viewing must be screen or room; choose the intended viewing context before evaluating type size',page,{viewing});
    const direct=name=>Array.from(page.children).filter(el=>el.classList.contains(name));
    const groups={header:direct('deck-header'),body:direct('deck-body'),footer:direct('deck-footer')};
    if(pageRoots.length!==1||Object.values(groups).some(items=>items.length!==1)){
      add('layout-contract-invalid','error','A .deck-page needs exactly one direct .deck-header, .deck-body and .deck-footer',page,
        {pageCount:pageRoots.length,regions:Object.fromEntries(Object.entries(groups).map(([name,items])=>[name,items.length]))});
    }else{
      const header=groups.header[0],body=groups.body[0],footer=groups.footer[0];
      const hr=header.getBoundingClientRect(),br=body.getBoundingClientRect(),fr=footer.getBoundingClientRect();
      const css=getComputedStyle(body),px=name=>parseFloat(css[name])||0;
      const bottomReserve=px('paddingBottom');
      const usable={left:br.left+px('borderLeftWidth')+px('paddingLeft'),top:br.top+px('borderTopWidth')+px('paddingTop'),
        right:br.right-px('borderRightWidth')-px('paddingRight'),bottom:br.bottom-px('borderBottomWidth')-bottomReserve};
      usable.width=Math.max(0,usable.right-usable.left);usable.height=Math.max(0,usable.bottom-usable.top);
      const bodyRuns=runs.filter(run=>body.contains(run.el));
      const primary=bodyRuns.filter(run=>!run.el.closest('.deck-caption, .deck-kicker'));
      const blocks=Array.from(body.querySelectorAll('.deck-block')).filter(el=>{
        const outer=el.parentElement.closest('.deck-block');
        return visible(el)&&!el.closest('.deck-caption')&&(!outer||!body.contains(outer));
      });
      // Measure only author transforms up through .deck-page. The player's
      // outer canvas scale is presentation zoom, not an attempt to shrink type.
      function bodyTextScale(el){
        let matrix=new DOMMatrix(),unknown=false;
        for(let cur=el;cur;cur=cur.parentElement){
          const cs=getComputedStyle(cur);
          let local=new DOMMatrix(cs.transform==='none'?undefined:cs.transform);
          if(!local.is2D)unknown=true;
          const factors=(cs.scale||'none').split(/\s+/);
          const number=value=>value?.endsWith('%')?parseFloat(value)/100:Number(value);
          if(factors[0]!=='none'){
            const x=number(factors[0]),y=factors.length>1?number(factors[1]):x;
            if(Number.isFinite(x)&&Number.isFinite(y))local=new DOMMatrix().scale(x,y).multiply(local);
            else unknown=true;
            if(factors.length>2&&number(factors[2])!==1)unknown=true;
          }
          // Independent rotations prevent a reliable 2D size estimate. Keep
          // that uncertainty visible as an advisory for the visual reviewer.
          if(cs.rotate&&cs.rotate!=='none')unknown=true;
          const zoom=Number(cs.zoom);
          if(Number.isFinite(zoom)&&zoom>0)local=new DOMMatrix().scale(zoom).multiply(local);
          matrix=local.multiply(matrix);
          if(cur===page)break;
        }
        const {a,b,c,d}=matrix,trace=a*a+b*b+c*c+d*d,det=a*d-b*c;
        const minScale=Math.sqrt(Math.max(0,(trace-Math.sqrt(Math.max(0,trace*trace-4*det*det)))/2));
        return {scale:round(minScale),unknown};
      }
      const primaryGeometry=primary.map(run=>{
        const geometry=bodyTextScale(run.el);
        return {element:label(run.el),text:run.text,fontSize:run.fontSize,...geometry,
          renderedFontEstimate:geometry.unknown?null:round(run.fontSize*geometry.scale)};
      });
      const declared=body.getAttribute('data-max-blocks')??page.getAttribute('data-max-blocks');
      const validBudget=declared===null||(/^\d+$/.test(declared)&&Number.isSafeInteger(Number(declared))&&Number(declared)>0);
      const maxBlocks=validBudget&&declared!==null?Number(declared):null;
      if(validBudget&&minBodyFontRecommended!==null) typeRegions={page,header,body,footer};
      layoutBudget={header:box(hr),body:box(br),footer:box(fr),available:box(usable),
        availableWidth:round(usable.width),availableHeight:round(usable.height),bottomReserve:round(bottomReserve),
        blocks:blocks.map(el=>({element:label(el),bounds:box(el.getBoundingClientRect())})),blockCount:blocks.length,
        maxBlocks,primaryTextRuns:primary.length,captionTextRuns:bodyRuns.length-primary.length,
        viewing,minBodyFont:primary.length?round(Math.min(...primary.map(run=>run.fontSize))):null,minBodyFontRecommended,
        minRenderedBodyFont:primaryGeometry.length&&primaryGeometry.every(item=>!item.unknown)?Math.min(...primaryGeometry.map(item=>item.renderedFontEstimate)):null,
        textScaleMethod:'minimum 2D singular scale within .deck-page, excluding player canvas zoom',
        transformedBodyText:primaryGeometry.filter(item=>item.unknown||item.scale<.999)};
      if(!validBudget) add('layout-contract-invalid','error','data-max-blocks must be a positive integer; omit it when the project does not set a block budget',body,{declared});
      if(!visible(header)||!visible(body)||!visible(footer)||usable.width<=0||usable.height<=0)
        add('body-no-capacity','error','Page regions must be visible and leave a positive body area; shorten the heading or split the page',body,{available:box(usable)});
      for(const [name,region,rect] of [['header',header,hr],['footer',footer,fr]]){
        const width=Math.min(br.right,rect.right)-Math.max(br.left,rect.left);
        const height=Math.min(br.bottom,rect.bottom)-Math.max(br.top,rect.top);
        if(width>options.tolerance&&height>options.tolerance)
          add('body-region-overlap','error','The body overlaps the '+name+' region; use normal flow and split excess content into another page',body,
            {other:label(region),intersection:{width:round(width),height:round(height)}});
      }
      const outside=(rect,bound)=>({left:Math.max(0,bound.left-rect.left),top:Math.max(0,bound.top-rect.top),
        right:Math.max(0,rect.right-bound.right),bottom:Math.max(0,rect.bottom-bound.bottom)});
      const exceeds=values=>Object.values(values).some(value=>value>options.tolerance);
      for(const [name,region,rect] of [['header',header,hr],['footer',footer,fr]]){
        for(const run of runs.filter(item=>region.contains(item.el))){
          // DOM Range includes font ascent/descent outside a tight CSS line
          // box. Allow only that small metric overhang, not an extra text line.
          const leading=parseFloat(getComputedStyle(run.el).lineHeight);
          const metricOverhang=Number.isFinite(leading)?Math.min(4,Math.max(0,(Math.max(...run.rects.map(r=>r.height))-leading)/2)):0;
          const verticalTolerance=options.tolerance+metricOverhang;
          const outsideRects=run.rects.filter(textRect=>{
            const excess=outside(textRect,rect);
            return excess.left>options.tolerance||excess.right>options.tolerance||excess.top>verticalTolerance||excess.bottom>verticalTolerance;
          });
          if(outsideRects.length)add('region-text-outside','error','Text exceeds its '+name+' region; let the region grow in normal flow and split excess content',run.el,
            {region:name,bounds:box(rect),text:run.text,rects:outsideRects.map(box)});
        }
      }
      const regions=[['header',header,hr],['body',body,br],['footer',footer,fr]];
      for(const run of runs.filter(item=>page.contains(item.el)&&!regions.some(([,region])=>region.contains(item.el))))
        add('layout-text-unassigned','error','Place visible text inside its header, body or footer region so it participates in page capacity',run.el,
          {text:run.text,rects:run.rects.map(box)});
      for(const image of page.querySelectorAll('img')){
        if(!visible(image))continue;
        const rect=image.getBoundingClientRect(),owner=regions.find(([,region])=>region.contains(image));
        if(!owner)add('layout-image-unassigned','error','Place this image inside its header, body or footer region so it participates in page capacity',image,{bounds:box(rect)});
        for(const [name,bound] of [['slide',bounds],...(owner?[[owner[0],owner[2]]]:[])]){
          const excess=outside(rect,bound);
          if(exceeds(excess))add('layout-image-outside','error','Image exceeds its '+name+' boundary; resize its region or split the page',image,
            {region:name,bounds:box(bound),image:box(rect),excess:Object.fromEntries(Object.entries(excess).map(([key,value])=>[key,round(value)]))});
        }
      }
      const unmarked=primary.filter(run=>{
        const block=run.el.closest('.deck-block');return !block||!body.contains(block);
      });
      if(unmarked.length)add('body-unmarked-content','warning','Primary text is not assigned to a .deck-block; mark semantic units before relying on the page block budget',unmarked[0].el,
        {count:unmarked.length,samples:unmarked.slice(0,8).map(run=>({element:label(run.el),text:run.text}))});
      const scaled=primaryGeometry.filter(item=>item.unknown||item.scale<.999);
      if(scaled.length)add('body-text-scaled','warning','An authored transform reduces primary text or prevents reliable size estimation; visually assess its rendered readability',primary[primaryGeometry.indexOf(scaled[0])].el,
        {count:scaled.length,samples:scaled.slice(0,8)});
      for(const run of bodyRuns){
        const outsideRects=run.rects.filter(rect=>exceeds(outside(rect,br)));
        if(outsideRects.length) add('body-text-outside','error','Body text exceeds its allocated region; split this page instead of shrinking or clipping text',run.el,
          {text:run.text,body:box(br),rects:outsideRects.map(box)});
      }
      // Element boxes protect images/cards as well as glyphs. Text includes
      // captions: their smaller type does not exempt them from the reserved gap.
      const occupied=bodyRuns.flatMap(run=>run.rects.map(rect=>({el:run.el,rect,text:run.text}))).concat(
        Array.from(new Set([...blocks,...body.querySelectorAll('img')])).filter(visible).map(el=>({el,rect:el.getBoundingClientRect()})));
      const breaches=new Map();
      for(const item of occupied){
        const excess=outside(item.rect,usable);
        if(!exceeds(excess)) continue;
        const key=label(item.el),previous=breaches.get(key);
        if(previous) for(const side of Object.keys(excess)) previous.excess[side]=Math.max(previous.excess[side],excess[side]);
        else breaches.set(key,{...item,excess});
      }
      for(const {el,text,excess} of breaches.values()) add('body-capacity-exceeded','error',
        'Content exceeds the body content area defined by its CSS padding; adjust the content or its allocated region',el,
        {text,available:box(usable),bottomReserve:round(bottomReserve),excess:Object.fromEntries(Object.entries(excess).map(([key,value])=>[key,round(value)]))});
      const tooSmall=minBodyFontRecommended===null?[]:primary.filter(run=>run.fontSize<minBodyFontRecommended);
      if(tooSmall.length) add('body-min-font','warning','Primary body text is below the '+minBodyFontRecommended+'px recommendation for '+viewing+' viewing; visually assess readability at the intended viewing size',tooSmall[0].el,
        {viewing,threshold:minBodyFontRecommended,count:tooSmall.length,samples:tooSmall.slice(0,8).map(run=>({text:run.text,fontSize:run.fontSize,element:label(run.el)}))});
      if(maxBlocks!==null&&blocks.length>maxBlocks) add('body-block-budget','warning','The page exceeds its explicitly declared semantic block budget; review the layout or revise the project budget',body,
        {count:blocks.length,maxBlocks});
      if(bodyRuns.length&&!primary.length) add('body-caption-only','warning',
        'All body text is marked as captions; visually confirm this fits the intended image-led composition',body);
    }
  }
  // Auxiliary labels have a different reading role from the explanation. Apply
  // this only inside a valid capacity contract; legacy HTML keeps its existing
  // threshold, and an explicit minFont always remains a global advisory floor.
  const tinyBody=runs.filter(run=>{
    if(run.fontSize>=16||run.characterCount<20)return false;
    if(run.el.closest('h1,h2,h3,h4,h5,h6,code,pre,kbd,samp,.mono,.deck-footer,.deck-caption,.deck-kicker'))return false;
    return run.el.tagName==='P'||run.el.tagName==='LI'||!!run.el.closest('.deck-body, .deck-copy');
  });
  if(tinyBody.length) add('body-type-too-small','warning','Body text is below 16px; enlarge it or split the page',tinyBody[0].el,
    {count:tinyBody.length,samples:tinyBody.slice(0,8).map(run=>({text:run.text,fontSize:run.fontSize,element:label(run.el)}))});
  const smallGroups=new Map();
  for(const run of runs){
    let role='text';
    if(typeRegions&&[typeRegions.header,typeRegions.body,typeRegions.footer].some(region=>region.contains(run.el))){
      if(typeRegions.footer.contains(run.el))role='footer';
      else {
        const caption=run.el.closest('.deck-caption, .deck-kicker');
        if(caption&&typeRegions.page.contains(caption))role='caption';
      }
    }
    const threshold=options.minFont??(role==='caption'?16:role==='footer'?14:24);
    if(run.fontSize>=threshold)continue;
    const key=role+':'+threshold;
    if(!smallGroups.has(key))smallGroups.set(key,{role,threshold,runs:[]});
    smallGroups.get(key).runs.push(run);
  }
  for(const {role,threshold,runs:small} of smallGroups.values()) {
    // Header labels must not consume the whole sample budget and hide a page
    // of small explanations. Show the longest run at each size first, then
    // fill with long runs. Counts describe text nodes, not lines or problems.
    const bySize=new Map();
    for(const run of small){
      if(!bySize.has(run.fontSize))bySize.set(run.fontSize,[]);
      bySize.get(run.fontSize).push(run);
    }
    const ranked=Array.from(bySize.entries()).sort((a,b)=>a[0]-b[0]).map(([fontSize,items])=>({
      fontSize,items:items.slice().sort((a,b)=>b.characterCount-a.characterCount)
    }));
    const selected=ranked.map(group=>group.items[0]).slice(0,8);
    for(const run of small.slice().sort((a,b)=>b.characterCount-a.characterCount)){
      if(selected.length>=8)break;
      if(!selected.includes(run))selected.push(run);
    }
    add('small-text','warning',small.length+' small text runs (role: '+role+') need review at the intended viewing size',small[0].el,
      {role,threshold,count:small.length,
        fontSizeDistribution:ranked.map(({fontSize,items})=>({fontSize,count:items.length,characters:items.reduce((sum,run)=>sum+run.characterCount,0)})),
        samples:selected.map(run=>({text:run.text,fontSize:run.fontSize,characterCount:run.characterCount,role,threshold,element:label(run.el)}))});
  }
  // Distinct semantic blocks only: inline emphasis in one paragraph stays one
  // object; a parent's direct text can still collide with a child paragraph.
  // Range boxes include font ascenders and
  // descenders, so shallow touching remains below the review threshold.
  const intersections=new Map();
  for(let i=0;i<runs.length;i++) for(let j=i+1;j<runs.length;j++){
    const a=runs[i],b=runs[j];
    if(a.group===b.group) continue;
    const key=label(a.group)+'\n'+label(b.group);
    for(const ar of a.rects) for(const br of b.rects){
      const w=Math.min(ar.right,br.right)-Math.max(ar.left,br.left),h=Math.min(ar.bottom,br.bottom)-Math.max(ar.top,br.top);
      if(w<=3||h<=2||h/Math.min(ar.height,br.height)<.18||w*h<40) continue;
      const previous=intersections.get(key);
      if(!previous||w*h>previous.area) intersections.set(key,{a,b,w,h,area:w*h,ratio:w*h/Math.min(ar.width*ar.height,br.width*br.height)});
    }
  }
  for(const {a,b,w,h,area,ratio} of intersections.values()) add('text-overlap','warning','Independent text blocks intersect; review or repair before delivery',a.group,{other:label(b.group),text:a.text,otherText:b.text,intersection:{width:round(w),height:round(h),area:round(area),fractionOfSmallerLine:round(ratio)}},b.group);
  // Hit testing is evidence for ordinary opaque foregrounds, not a complete
  // paint/contrast solver. Only consider actual foreground hits before the text
  // owner; for SVG gaps between glyphs, require later SVG paint order as well.
  // pointer-events:none shapes, pseudo-elements and complex masks still need
  // screenshot review. Never disable authored CSS to make this test pass.
  function solidForeground(el){
    const cs=getComputedStyle(el);
    if(Number(cs.opacity)<.95) return false;
    if(el instanceof SVGElement){
      if(!/^(rect|circle|ellipse|path|polygon|image)$/.test(el.tagName)) return false;
      return el.tagName==='image'||(cs.fill!=='none'&&Number(cs.fillOpacity)>=.95);
    }
    if(/^(IMG|CANVAS|VIDEO)$/.test(el.tagName)) return true;
    const match=cs.backgroundColor.match(/^rgba?\((.*)\)$/);
    const alpha=match ? (match[1].split(',').length===4 ? Number(match[1].split(',')[3]) : 1) : 0;
    return alpha>=.95 || cs.backgroundImage!=='none';
  }
  const occlusions=new Map();
  for(const run of runs){
    for(const rect of run.rects){
      const y=(rect.top+rect.bottom)/2;
      for(const fraction of [.2,.5,.8]){
        const x=rect.left+rect.width*fraction;
        if(x<bounds.left||x>bounds.right||y<bounds.top||y>bounds.bottom) continue;
        const stack=document.elementsFromPoint(x,y), ownerIndex=stack.indexOf(run.el);
        for(let i=0;i<stack.length && (ownerIndex<0||i<ownerIndex);i++){
          const foreground=stack[i];
          if(foreground===run.el||foreground.contains(run.el)||!slide.contains(foreground)||!solidForeground(foreground)) continue;
          if(ownerIndex<0){
            if(!(run.el instanceof SVGElement)||!(foreground instanceof SVGElement)||run.el.ownerSVGElement!==foreground.ownerSVGElement||!(run.el.compareDocumentPosition(foreground)&Node.DOCUMENT_POSITION_FOLLOWING)) continue;
          }
          const key=label(run.el)+'\n'+label(foreground);
          const previous=occlusions.get(key)||{run,foreground,samples:0}; previous.samples++;occlusions.set(key,previous);break;
        }
      }
    }
  }
  for(const {run,foreground,samples} of occlusions.values()) add('text-occluded','warning','Text sampling hits an opaque foreground; visually verify that text is readable',run.el,{text:run.text,coveredBy:label(foreground),samples},foreground);
  for(const im of slide.querySelectorAll('img')){
    const src=im.currentSrc||im.getAttribute('src')||'';
    if(!src.trim()||!im.complete||!im.naturalWidth) add('image-failed','error','Image is empty or failed to decode',im,{src});
    else if(visible(im)){
      const r=im.getBoundingClientRect();signatures.push({element:label(im),text:'[image]',rects:[box(r)]});
      if(r.width<1||r.height<1) add('image-zero-size','error','Loaded image has no visible area',im,{src});
    }
  }
  // Media clipping/occlusion: an illustration cut by its container or covered
  // by a later opaque layer is usually a sizing/stacking bug. The author can
  // exempt an intentional crop or overlap with data-web-check-allow.
  const mediaClip=(el,r)=>{
    let worst=0,by=null;
    for(let cur=el.parentElement;cur&&cur!==slide;cur=cur.parentElement){
      const cs=getComputedStyle(cur),clipX=/^(hidden|clip|auto|scroll)$/.test(cs.overflowX),clipY=/^(hidden|clip|auto|scroll)$/.test(cs.overflowY);
      if(!clipX&&!clipY)continue;
      const c=cur.getBoundingClientRect();
      const left=Math.max(r.left,c.left),right=Math.min(r.right,c.right),top=Math.max(r.top,c.top),bottom=Math.min(r.bottom,c.bottom);
      const fraction=1-Math.max(0,right-left)*Math.max(0,bottom-top)/Math.max(1,r.width*r.height);
      if(fraction>worst){worst=fraction;by=label(cur);}
    }
    return worst>.05?{fraction:round(worst),clippedBy:by}:null;
  };
  const opaqueForeground=el=>{
    if(el instanceof SVGElement){
      if(!/^(rect|circle|ellipse|path|polygon|image)$/.test(el.tagName))return false;
      const cs=getComputedStyle(el);
      return el.tagName==='image'||(cs.fill!=='none'&&Number(cs.fillOpacity)>=.95);
    }
    if(/^(IMG|CANVAS|VIDEO)$/.test(el.tagName))return true;
    const cs=getComputedStyle(el),match=cs.backgroundColor.match(/^rgba?\((.*)\)$/);
    const alpha=match?(match[1].split(',').length===4?Number(match[1].split(',')[3]):1):0;
    return alpha>=.9;
  };
  const mediaCover=(el,r)=>{
    let covered=0,total=0,by=null;
    for(const fy of [.2,.5,.8])for(const fx of [.2,.5,.8]){
      const x=r.left+r.width*fx,y=r.top+r.height*fy;
      if(x<bounds.left||x>bounds.right||y<bounds.top||y>bounds.bottom)continue;
      total++;
      const stack=document.elementsFromPoint(x,y);
      for(const node of stack){
        if(node===el||el.contains(node)||node.contains(el)||!slide.contains(node))continue;
        if(!opaqueForeground(node))continue;
        covered++;if(!by)by=label(node);break;
      }
    }
    return total&&covered/total>.3?{fraction:round(covered/total),coveredBy:by}:null;
  };
  for(const media of slide.querySelectorAll('img, svg')){
    if(!visible(media))continue;
    const r=media.getBoundingClientRect();
    if(r.width<80||r.height<80)continue;
    const kind=media.tagName.toLowerCase();
    // Full-bleed backgrounds behind content cards are a normal composition; only
    // small/illustrative media get the clipping/occlusion review by default.
    const classes=(media.getAttribute('class')||'')+' '+((media.parentElement&&media.parentElement.getAttribute('class'))||'');
    const backdrop=/(^|\s)(bg|background|backdrop|full-bleed|bleed)(\s|$)/i.test(classes)||(r.width*r.height)/Math.max(1,bounds.width*bounds.height)>=.5;
    if(backdrop)continue;
    const clipped=mediaClip(media,r);
    if(clipped)add('media-clipped','warning','Media is clipped by an overflow container; keep the subject inside the visible area or exempt an intentional crop',media,{kind,fraction:clipped.fraction,clippedBy:clipped.clippedBy,bounds:box(r)});
    const covered=mediaCover(media,r);
    if(covered)add('media-occluded','warning','Media is substantially covered by an opaque element; reorder layers or move the subject',media,{kind,fraction:covered.fraction,coveredBy:covered.coveredBy,bounds:box(r)});
  }
  // A declared raster-only policy is checked against the final DOM/computed
  // resources too: author scripts and external styles can add SVG after compile.
  // This identifies recognizable SVG; it does not prove an image's provenance.
  if(document.querySelector('meta[name="deck-media-policy"][content="generated-raster"]')){
    const seen=new Set();
    const isSvgUrl=value=>{
      let decoded=String(value||'').trim();
      try{decoded=decodeURIComponent(decoded);}catch(_){}
      return /^data:image\/svg\+xml(?:[;,]|$)/i.test(decoded)||/\.svg(?:[?#]|$)/i.test(decoded);
    };
    const flag=(el,source,value)=>{
      const key=label(el)+'\n'+source+'\n'+value;if(seen.has(key))return;seen.add(key);
      add('media-policy','error','This deck declares a raster-only policy; replace SVG with an asset allowed by the project',el,{source,value});
    };
    for(const svg of slide.querySelectorAll('svg'))flag(svg,'inline-svg','<svg>');
    for(const el of [slide,...slide.querySelectorAll('*')]){
      const resources=[];
      if(el.tagName==='IMG')resources.push(['img',el.currentSrc||el.getAttribute('src')]);
      if(el.tagName==='OBJECT')resources.push(['object',el.getAttribute('data')]);
      if(el.tagName==='EMBED')resources.push(['embed',el.getAttribute('src')]);
      for(const [kind,value] of resources)if(isSvgUrl(value))flag(el,kind,value);
      for(const pseudo of [null,'::before','::after']){
        const style=getComputedStyle(el,pseudo);
        for(const property of ['backgroundImage','maskImage','webkitMaskImage']){
          const value=style[property]||'';
          for(const match of value.matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\s*\)/gi)){
            const resource=match[1]??match[2]??match[3];
            if(isSvgUrl(resource))flag(el,(pseudo||'element')+':'+property,resource);
          }
        }
      }
    }
  }
  const context=document.createElement('canvas').getContext('2d');
  function color(value){context.fillStyle='#012345';context.fillStyle=value;return context.fillStyle;}
  for(const el of slide.querySelectorAll('svg text[fill],svg tspan[fill]')){
    const declared=el.getAttribute('fill'),computed=getComputedStyle(el).fill;
    if(visible(el)&&declared&&!/^(none|inherit|currentColor|url\()/i.test(declared)&&color(declared)!==color(computed))
      add('svg-fill-overridden','warning','CSS overrides the SVG text fill attribute; verify contrast on its actual background',el,{declared,computed,text:el.textContent.trim().slice(0,100)});
  }
  for(const el of slide.querySelectorAll('[data-web-check-allow]')){
    if(!(el.getAttribute('data-web-check-reason')||'').trim()) issues.push({code:'invalid-exemption',severity:'error',message:'An exemption requires a nonempty data-web-check-reason',element:label(el)});
    const supported=['text-overlap','text-mask','svg-fill-overridden','text-occluded','small-text','media-clipped','media-occluded','body-type-too-small'];
    const invalid=(el.getAttribute('data-web-check-allow')||'').split(/\s+/).filter(code=>code&&!supported.includes(code));
    if(invalid.length) issues.push({code:'invalid-exemption',severity:'error',message:'Only review/advisory checks can be exempted; hard errors always block',element:label(el),invalid});
  }
  return {slide:Number(slide.dataset.slide),title:slide.dataset.title||'',bounds:box(bounds),textRuns:runs.length,...(layoutBudget?{layoutBudget}:{}),issues,exemptions,signatures};
};
"""


async def _inspect(path: Path, *, chrome: str, timeout: float, stability_ms: int,
                   min_font: float | None, tolerance: float) -> dict:
    connect = _connect()
    report = {"file": str(path), "coordinateSpace": "CSS pixels at 1600×900", "pages": [],
              "issues": [], "scope": "completed export frames; DOM text and image geometry"}
    with tempfile.TemporaryDirectory(prefix="deck-web-check-") as folder:
        profile = Path(folder) / "profile"
        proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                 "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                                 "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
                                 f"--user-data-dir={profile}", "about:blank"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            target = None
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"Chrome exited with status {proc.returncode}")
                try:
                    port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                        targets = json.load(response)
                    target = next((t["webSocketDebuggerUrl"] for t in targets if t.get("type") == "page"), None)
                    if target:
                        break
                except (OSError, ValueError, IndexError):
                    pass
                await asyncio.sleep(.05)
            if not target:
                raise RuntimeError("Chrome CDP startup timed out")
            async with connect(target, max_size=None, open_timeout=timeout) as ws:
                sequence = 0
                requests = {}

                async def command(method, params=None):
                    nonlocal sequence
                    sequence += 1
                    own_id = sequence
                    await ws.send(json.dumps({"id": own_id, "method": method, "params": params or {}}))
                    async def receive():
                        while True:
                            message = json.loads(await ws.recv())
                            event, data = message.get("method"), message.get("params", {})
                            if event == "Network.requestWillBeSent":
                                requests[data["requestId"]] = {"url": data["request"]["url"], "type": data.get("type")}
                            elif event == "Network.loadingFailed":
                                request = requests.get(data["requestId"], {})
                                report["issues"].append({"code": "resource-failed", "severity": "error", "message": data.get("errorText"), **request})
                            elif event == "Runtime.exceptionThrown":
                                details = data.get("exceptionDetails", {})
                                report["issues"].append({"code": "script-error", "severity": "error", "message": details.get("exception", {}).get("description", details.get("text"))})
                            if message.get("id") == own_id:
                                if "error" in message:
                                    raise RuntimeError(f"CDP {method}: {message['error']}")
                                return message.get("result", {})
                    return await asyncio.wait_for(receive(), timeout=timeout)

                async def evaluate(expression):
                    result = await command("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
                    if result.get("exceptionDetails"):
                        details = result["exceptionDetails"]
                        raise RuntimeError(details.get("exception", {}).get("description", details.get("text", "JavaScript evaluation failed")))
                    return result.get("result", {}).get("value")

                for method in ("Page.enable", "Runtime.enable", "Network.enable"):
                    await command(method)
                await command("Emulation.setDeviceMetricsOverride", {"width": 1600, "height": 900, "deviceScaleFactor": 1, "mobile": False})
                await command("Page.addScriptToEvaluateOnNewDocument", {"source": "window.__recording=true;"})
                await command("Page.navigate", {"url": path.as_uri()})
                deadline = time.monotonic() + timeout
                while not await evaluate("document.readyState==='complete'"):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Document load timed out")
                    await asyncio.sleep(.05)
                contract = await evaluate("!!(document.querySelector('meta[name=\"deck-web-runtime\"]') && window.__deck && typeof __deck.seek==='function' && Array.isArray(window.__deck_timeline))")
                if not contract:
                    raise RuntimeError("Expected a compiled web_deck.py artifact with its runtime and timeline")
                try:
                    readiness = await evaluate("""(async()=>{
                      if(document.fonts) await document.fonts.ready;
                      const images=await Promise.allSettled(Array.from(document.images).map(async im=>{im.loading='eager';if(im.decode)await im.decode();if(!im.complete||!im.naturalWidth)throw Error('Image failed: '+im.src)}));
                      let runtimeError=null;
                      try{await window.__deck_charts_ready;}catch(e){runtimeError=String(e);}
                      return {runtimeError,images:images.filter(r=>r.status==='rejected').map(r=>String(r.reason)),fonts:document.fonts?Array.from(document.fonts).filter(f=>f.status==='error').map(f=>f.family):[]};
                    })()""")
                    if readiness["runtimeError"] or readiness["images"] or readiness["fonts"]:
                        report["issues"].append({"code": "readiness-failed", "severity": "error", "message": "Fonts, images or the author/runtime readiness promise failed", "details": readiness})
                except (TimeoutError, asyncio.TimeoutError):
                    report["issues"].append({"code": "readiness-timeout", "severity": "error", "message": f"Resources were not ready within {timeout:g}s"})
                await evaluate(COLLECT_JS)
                timeline = await evaluate("window.__deck_timeline")
                options = json.dumps({"tolerance": tolerance, "minFont": min_font})
                for index, step in enumerate(timeline):
                    # A tiny hold offset avoids floating-point addition rounding a
                    # reveal just short of its declared completion.
                    when = step["start"] + step["enter"] + min(.001, step["hold"] / 2)
                    expression = """(async()=>{
                      window.__deck.seek(TIME);
                      await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                      const slide=document.querySelectorAll('section.slide')[INDEX];
                      const first=window.__webCheckCollect(slide,OPTIONS), movements=[];
                      let previous=first.signatures, start=performance.now(), samples=1;
                      while(performance.now()-start<DURATION){
                        await new Promise(r=>requestAnimationFrame(r));
                        const current=window.__webCheckCollect(slide,OPTIONS).signatures; samples++;
                        if(JSON.stringify(current)!==JSON.stringify(previous)){
                          for(let i=0;i<Math.max(current.length,previous.length);i++){
                            const a=first.signatures[i],b=current[i];
                            if(!a||!b||a.text!==b.text||a.rects.length!==b.rects.length){movements.push({element:(b||a).element,delta:null,reason:'Text/line count changed'});continue;}
                            let delta=0;
                            a.rects.forEach((r,j)=>['x','y','w','h'].forEach(k=>delta=Math.max(delta,Math.abs(r[k]-b.rects[j][k]))));
                            if(delta>TOLERANCE) movements.push({element:b.element,delta:Math.round(delta*100)/100,reason:'Geometry changed after completed seek'});
                          }
                        }
                        previous=current;
                      }
                      const unique=Array.from(new Map(movements.map(m=>[m.element,m])).values());
                      if(unique.length) first.issues.push({code:'unstable-layout',severity:'error',message:'Content moved after completed seek',movements:unique});
                      first.stability={durationMs:DURATION,samples,movingElements:unique.length};
                      delete first.signatures;return first;
                    })()""".replace("TIME", json.dumps(when)).replace("INDEX", str(index)).replace("OPTIONS", options).replace("DURATION", str(stability_ms)).replace("TOLERANCE", str(tolerance))
                    report["pages"].append(await evaluate(expression))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    return summarize(report)


def summarize(report: dict) -> dict:
    findings = report.get("issues", []) + [issue for page in report.get("pages", []) for issue in page["issues"]]
    errors = sum(issue["severity"] == "error" for issue in findings)
    warnings = sum(issue["severity"] == "warning" for issue in findings)
    review = sum(bool(issue.get("requiresReview")) for issue in findings)
    report["summary"] = {"pages": len(report.get("pages", [])), "errors": errors, "warnings": warnings,
                         "review": review,
                         "exemptions": sum(len(p.get("exemptions", [])) for p in report.get("pages", [])),
                         "status": "failed" if errors else "needs_review" if review else "passed"}
    return report


def exit_code(report: dict, strict: bool = False) -> int:
    """Keep uncertain collisions out of the automatic success path."""
    summary = report["summary"]
    return 1 if summary["errors"] else 2 if summary["review"] or (strict and summary["warnings"]) else 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def inspect(html: str | Path, *, chrome: str | None = None, timeout: float = 30,
            stability_ms: int = 350, min_font: float | None = None, tolerance: float = 1) -> dict:
    path = Path(html).resolve()
    if not path.is_file():
        raise ValueError(f"HTML file does not exist: {path}")
    if not math.isfinite(timeout) or timeout <= 0 or not 100 <= stability_ms <= 5000:
        raise ValueError("timeout must be positive; stability-ms must be 100–5000")
    if ((min_font is not None and (not math.isfinite(min_font) or min_font <= 0))
            or not math.isfinite(tolerance) or not 0 <= tolerance <= 4):
        raise ValueError("min-font must be positive; tolerance must be 0–4 CSS px")
    initial_bytes = path.read_bytes()
    captured_at = _utc_now()
    initial_sha = hashlib.sha256(initial_bytes).hexdigest()
    try:
        binary = browser.find_chrome(chrome)
        report = asyncio.run(_inspect(path, chrome=binary, timeout=timeout, stability_ms=stability_ms, min_font=min_font, tolerance=tolerance))
    except (RuntimeError, ValueError, OSError, TimeoutError, asyncio.TimeoutError) as exc:
        report = {"file": str(path), "pages": [], "issues": [{"code": "inspection-failed", "severity": "error", "message": str(exc)}]}
    # Another author may be rebuilding this same path while Chrome reads it.
    # A geometry result must never certify a different revision at that path.
    try:
        final_bytes = path.read_bytes()
    except OSError as exc:
        report["issues"].append({"code": "input-changed", "severity": "error",
                                 "message": f"Input became unreadable during inspection: {exc}"})
    else:
        if final_bytes != initial_bytes:
            report["issues"].append({"code": "input-changed", "severity": "error",
                                     "message": "Input HTML changed during inspection; rerun against a stable artifact",
                                     "observedHtmlSha256": hashlib.sha256(final_bytes).hexdigest()})
    report.update(capturedAt=captured_at, checkedAt=_utc_now(), htmlSha256=initial_sha)
    return summarize(report)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--json", type=Path, help="Write the complete machine-readable report")
    parser.add_argument("--chrome")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--stability-ms", type=int, default=350)
    parser.add_argument("--min-font", type=float, help="Global small-type advisory floor; default 24px, with 16px captions and 14px footers in valid .deck-page layouts. Viewing-context recommendations remain independent advisories.")
    parser.add_argument("--tolerance", type=float, default=1)
    parser.add_argument("--strict", action="store_true", help="Also exit 2 for advisory warnings (errors always exit 1)")
    args = parser.parse_args(argv)
    if args.json:
        if args.json.is_symlink():
            parser.error("Report target must not be a symlink")
        if args.json.resolve() == args.html.resolve() or (args.json.exists() and args.html.exists() and args.json.samefile(args.html)):
            parser.error("Report target must not overwrite the input HTML")
        if not args.json.parent.is_dir() or (args.json.exists() and not args.json.is_file()):
            parser.error("Report target needs an existing directory and must be a regular file")
    try:
        report = inspect(args.html, chrome=args.chrome, timeout=args.timeout, stability_ms=args.stability_ms, min_font=args.min_font, tolerance=args.tolerance)
    except (RuntimeError, ValueError, OSError, TimeoutError, asyncio.TimeoutError) as exc:
        report = summarize({"file": str(args.html.resolve()), "pages": [], "issues": [{"code": "inspection-failed", "severity": "error", "message": str(exc)}]})
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(f"{summary['status'].upper()}: {summary['pages']} pages · {summary['errors']} errors · {summary['review']} review findings · {summary['warnings'] - summary['review']} advisories · {summary['exemptions']} explicit exemptions")
    for page in [{"slide": "—", "issues": report["issues"]}] + report["pages"]:
        for issue in page["issues"]:
            print(f"  [{issue['severity']}] page {page['slide']} {issue['code']}: {issue['message']} {issue.get('element', '')}")
    if summary["review"]:
        print("Review warnings require screenshot review or a reasoned local exception; this is not a visual-quality pass.")
    return exit_code(report, args.strict)


if __name__ == "__main__":
    sys.exit(main())
