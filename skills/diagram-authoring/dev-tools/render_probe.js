// Runs only in the locally created, network-disabled SVG inspection page.
(async () => {
  const result = document.getElementById('result');
  try {
    const xml = new TextDecoder().decode(Uint8Array.from(atob(document.getElementById('svg-data').textContent), c => c.charCodeAt(0)));
    const parsed = new DOMParser().parseFromString(xml, 'image/svg+xml');
    if (parsed.querySelector('parsererror')) throw Error('SVG XML parse failed');
    const svg = document.importNode(parsed.documentElement, true);
    document.body.append(svg);
    await document.fonts.ready;
    const rect = e => {
      const r = e.getBoundingClientRect();
      return {x:r.x, y:r.y, width:r.width, height:r.height};
    };
    const visible = e => {
      for (let p=e; p && p !== document.body; p=p.parentElement) {
        const s = getComputedStyle(p);
        if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
        if (p.parentElement && p.parentElement.localName === 'switch' && p !== p.parentElement.firstElementChild) return false;
      }
      return !e.closest('defs, metadata, title, desc');
    };
    const texts = [], textElements = [], clipped = [];
    const intersection = (a,b) => Math.max(0,Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x))
      * Math.max(0,Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y));
    const record = (el, text, box) => {
      if (!text.trim() || !visible(el)) return;
      const css = getComputedStyle(el);
      const matrix = typeof el.getScreenCTM === 'function' ? el.getScreenCTM() : svg.getScreenCTM();
      const scale = matrix ? Math.hypot(matrix.a,matrix.b) : 1;
      texts.push({text, box, font:css.fontFamily, px:parseFloat(css.fontSize)*scale,
                  cell:el.closest('[data-cell-id]')?.getAttribute('data-cell-id') || null});
      textElements.push(el);
      // Check actual range/text bounds against rectangular clipping ancestors.
      // Do not mistake every foreignObject for a clip: overflow can be visible.
      for (let p=el; p && p!==svg; p=p.parentElement) {
        const style=getComputedStyle(p);
        const clipsX=['hidden','clip','scroll','auto'].includes(style.overflowX);
        const clipsY=['hidden','clip','scroll','auto'].includes(style.overflowY);
        if (p.localName==='text' || (!clipsX && !clipsY)) continue;
        const boundary=rect(p);
        if (!boundary.width || !boundary.height) continue;
        if ((clipsX && (box.x<boundary.x-1.5 || box.x+box.width>boundary.x+boundary.width+1.5))
          || (clipsY && (box.y<boundary.y-1.5 || box.y+box.height>boundary.y+boundary.height+1.5))) {
          clipped.push({text,box,boundary,kind:p.localName}); break;
        }
      }
    };
    for (const el of svg.querySelectorAll('text')) record(el, el.textContent, rect(el));
    for (const fo of svg.querySelectorAll('foreignObject')) {
      if (!visible(fo)) continue;
      const walker=document.createTreeWalker(fo,NodeFilter.SHOW_TEXT);
      let n;
      while ((n=walker.nextNode())) {
        if (!n.textContent.trim()) continue;
        const range=document.createRange();range.selectNodeContents(n);
        record(n.parentElement,n.textContent,rect(range));
      }
    }
    const background = [...svg.children].find(e => e.localName === 'rect');
    const graphicElements=[...svg.querySelectorAll('path,rect,ellipse,circle,polygon,polyline,line,image')]
      .filter(e=>e!==background && visible(e));
    const graphics=graphicElements.map(e=>({kind:e.localName,box:rect(e)}));
    const overlaps=[];
    for (let i=0;i<texts.length;i++) for (let j=i+1;j<texts.length;j++) {
      const a=texts[i],b=texts[j],area=Math.min(a.box.width*a.box.height,b.box.width*b.box.height);
      // Tolerate sub-pixel font box contact; report substantial overlap only.
      if (area>0 && intersection(a.box,b.box)/area>.18)
        overlaps.push({first:a.text,second:b.text,first_box:a.box,second_box:b.box});
    }
    const opaque = el => {
      let opacity=1;
      for (let p=el;p && p!==document.body;p=p.parentElement) opacity*=Number(getComputedStyle(p).opacity);
      const css=getComputedStyle(el),fill=css.fill;
      const alpha=fill.startsWith('rgba(') ? Number(fill.split(',').pop().replace(')','')) : 1;
      return fill!=='none' && fill!=='transparent' && opacity*Number(css.fillOpacity)*alpha>.98;
    };
    const occluded=[];
    for (let i=0;i<texts.length;i++) {
      const t=texts[i],el=textElements[i];
      for (let j=0;j<graphicElements.length;j++) {
        const g=graphicElements[j];
        if (!(el.compareDocumentPosition(g)&Node.DOCUMENT_POSITION_FOLLOWING)
          || !opaque(g) || typeof g.isPointInFill!=='function'
          || intersection(t.box,graphics[j].box)<=0) continue;
        let covered=0,total=0;
        const matrix=g.getScreenCTM();if(!matrix)continue;
        for (const x of [.2,.5,.8]) for (const y of [.3,.7]) {
          const point=new DOMPoint(t.box.x+t.box.width*x,t.box.y+t.box.height*y).matrixTransform(matrix.inverse());
          total++;if(g.isPointInFill(point))covered++;
        }
        if (covered/total>=.5) {occluded.push({text:t.text,box:t.box,cover:graphics[j],fraction:covered/total});break;}
      }
    }
    // Version-specific adapters inspect actual exported arrow paths, not source counts.
    const cells=[...svg.querySelectorAll('[data-cell-id]')].map(e=>({
      id:e.getAttribute('data-cell-id'), paths:[...e.querySelectorAll('path')].filter(visible).length
    }));
    const arrowGroups=[...svg.children].filter(e=>e.localName==='g' && e.getAttribute('stroke-linecap')==='round'
      && [...e.children].some(c=>c.localName==='g'));
    const arrows=arrowGroups.map(e=>[...e.querySelectorAll('path')].filter(visible).length);
    const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
    const fonts=[...new Set(texts.map(t=>t.font.split(',')[0].trim().replace(/^['"]|['"]$/g,'')))];
    const generic=new Set(['serif','sans-serif','monospace','system-ui','cursive','fantasy']);
    const available = family => {
      if (generic.has(family.toLowerCase())) return true;
      const sample='Wim0123456789汉字';
      return ['monospace','serif'].some(base=>{
        ctx.font=`32px ${base}`;const w=ctx.measureText(sample).width;
        ctx.font=`32px ${JSON.stringify(family)}, ${base}`;
        return Math.abs(ctx.measureText(sample).width-w)>0.01;
      });
    };
    const data={canvas:rect(svg), texts, graphics, cells, arrows, clipped, overlaps, occluded,
      font_status:document.fonts.status,
      fonts:fonts.map(family=>({family,available:available(family)})),
      failed_faces:[...document.fonts].filter(f=>f.status==='error').map(f=>f.family)};
    result.textContent=JSON.stringify(data);result.dataset.status='ok';
  } catch(e) { result.textContent=JSON.stringify({error:String(e)});result.dataset.status='error'; }
})();
