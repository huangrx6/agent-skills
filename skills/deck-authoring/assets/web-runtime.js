/* Authored HTML player. seek(t) is the only animation state transition. */
(function () {
  'use strict';
  var root = document.documentElement;
  var slides = Array.from(document.querySelectorAll('section.slide'));
  var timeline = window.__deck_timeline;
  var recording = window.__recording === true;
  var mode = recording ? 'record' : (new URLSearchParams(location.search).has('scroll') ? 'scroll' : 'present');
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var frames = [], plans = [], current = 0, raf = 0, generation = 0, ready = false;
  var status;
  root.classList.add('deck-web');
  root.dataset.deckMode = mode;

  slides.forEach(function (slide) {
    var frame = document.createElement('div');
    frame.className = 'deck-web-frame';
    var canvas = document.createElement('div');
    canvas.className = 'deck-web-canvas';
    slide.parentNode.insertBefore(frame, slide);
    frame.appendChild(canvas);
    canvas.appendChild(slide);
    frames.push(frame);
    var nodes = Array.from(slide.querySelectorAll('[data-reveal]'));
    if (slide.hasAttribute('data-reveal')) nodes.unshift(slide);
    plans.push(nodes.map(function (node) {
      var baseline = getComputedStyle(node);
      // Preserve authored centering and masks. Mixing unknown %, px or 3D values
      // with an entrance offset would otherwise snap when the original CSS returns.
      // An occupied motion property deliberately degrades that reveal to a fade.
      var kind = node.dataset.reveal;
      if ((kind === 'rise' && baseline.translate !== 'none') ||
          (kind === 'wipe' && baseline.clipPath !== 'none')) kind = 'fade';
      return {node: node, kind: kind, at: Number(node.dataset.at || 0),
        duration: Number(node.dataset.duration || .6), opacity: node.style.opacity,
        translate: node.style.translate, clip: node.style.clipPath,
        baseOpacity: Number(baseline.opacity)};
    }));
  });

  function cancel() { generation++; cancelAnimationFrame(raf); raf = 0; }
  function paint(index, seconds, settled) {
    plans[index].forEach(function (item) {
      var progress = settled ? 1 : Math.max(0, Math.min(1, (seconds - item.at) / item.duration));
      var ease = 1 - Math.pow(1 - progress, 3);
      if (progress === 1) {
        item.node.style.opacity = item.opacity;
        item.node.style.translate = item.translate;
        item.node.style.clipPath = item.clip;
      } else {
        item.node.style.opacity = String(item.baseOpacity * ease);
        item.node.style.translate = item.kind === 'rise' ? '0 ' + ((1 - ease) * 28) + 'px' : item.translate;
        item.node.style.clipPath = item.kind === 'wipe' ? 'inset(0 ' + ((1 - ease) * 100) + '% 0 0)' : item.clip;
      }
    });
  }
  function fit() {
    var scale = mode === 'record' ? 1 : Math.min(innerWidth / 1600,
      mode === 'scroll' ? Infinity : innerHeight / 900);
    root.style.setProperty('--deck-web-scale', String(scale));
  }
  function activate(index) {
    current = Math.max(0, Math.min(slides.length - 1, index));
    frames.forEach(function (frame, i) {
      frame.toggleAttribute('data-active', i === current);
      // Hidden pages must not retain focused controls or appear in the accessibility tree.
      frame.inert = mode !== 'scroll' && i !== current;
    });
    if (status) status.textContent = (current + 1) + ' / ' + slides.length + ' · ' + slides[current].dataset.title;
  }
  function settleAll() { plans.forEach(function (_, index) { paint(index, 0, true); }); }
  function seek(time) {
    if (!Number.isFinite(time)) throw new TypeError('seek(t) requires finite seconds');
    cancel();
    // An explicit seek is an export operation even when called in scroll mode.
    root.dataset.deckMode = 'record';
    mode = 'record';
    fit();
    var index = 0;
    for (var i = 1; i < timeline.length; i++) if (time >= timeline[i].start) index = i;
    activate(index);
    paint(index, Math.max(0, time - timeline[index].start), false);
    return index;
  }
  function play(index) {
    cancel();
    activate(index);
    if (mode !== 'present' || reduced.matches || !ready) {
      paint(current, 0, true);
      return;
    }
    var slideIndex = current, token = generation, started = performance.now();
    paint(slideIndex, 0, false);
    function tick(now) {
      if (generation !== token) return;
      var elapsed = (now - started) / 1000;
      paint(slideIndex, elapsed, false);
      if (elapsed < timeline[slideIndex].enter) raf = requestAnimationFrame(tick);
      else { paint(slideIndex, 0, true); raf = 0; }
    }
    raf = requestAnimationFrame(tick);
  }
  function go(index) { if (mode === 'present') play(index); }
  function setMode(value) {
    if (recording || !['present', 'scroll'].includes(value)) return;
    cancel(); mode = value; root.dataset.deckMode = mode; fit(); activate(current);
    settleAll();
  }
  function fullScreen() {
    var action = document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen();
    if (action && action.catch) action.catch(function () {});
  }
  if (!recording) {
    // Announce the active slide without adding visible chrome or reserving canvas space.
    status = document.createElement('div');
    status.className = '__deck_web_status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    document.body.appendChild(status);
  }
  document.addEventListener('keydown', function (event) {
    if (mode !== 'present' || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target.closest('input,textarea,select,button,a,[contenteditable]:not([contenteditable="false"]),[role="textbox"]')) return;
    if (event.key === 'ArrowRight' || event.key === 'PageDown') go(current + 1);
    else if (event.key === 'ArrowLeft' || event.key === 'PageUp') go(current - 1);
    else if (event.key.toLowerCase() === 'r') go(current);
    else if (event.key.toLowerCase() === 'f') fullScreen();
    else return;
    event.preventDefault();
  });
  addEventListener('resize', fit);
  reduced.addEventListener('change', function () { if (reduced.matches) { cancel(); settleAll(); } });
  addEventListener('beforeprint', function () { cancel(); settleAll(); frames.forEach(function (frame) { frame.inert = false; }); });
  addEventListener('afterprint', function () { activate(current); settleAll(); });
  window.__deck = {seek: seek};
  window.__deck_ui = {cur: function () { return current; }, total: slides.length, go: go,
    replay: function () { go(current); }, setMode: setMode,
    isPlaying: function () { return raf !== 0; }};
  fit(); activate(0); settleAll();
  // Capture helpers already await this promise; preserve any author chart promise.
  var authorReady = window.__deck_charts_ready;
  window.__deck_charts_ready = Promise.all([
    authorReady || Promise.resolve(),
    document.fonts ? document.fonts.ready : Promise.resolve(),
    Promise.all(Array.from(document.images).map(async function (image) {
      image.loading = 'eager';
      if (image.decode) await image.decode();
      if (!image.complete || !image.naturalWidth) throw new Error('image-not-ready: ' + image.src);
    }))
  ]).then(function () {
    ready = true;
    if (recording) seek(0);
    else if (mode === 'present') play(current);
    else settleAll();
    return true;
  });
  // Report a readable failure in the page without swallowing the rejection seen by exporters.
  window.__deck_charts_ready.catch(function (error) {
    if (status) {
      status.className = '__deck_web_error';
      status.setAttribute('role', 'alert');
      status.textContent = '资源加载失败'; status.title = String(error);
    }
    console.error('Deck resources failed', error);
  });
}());
