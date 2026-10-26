"""CSS and JS for the learning series pages.

Kept separate from build_series.py so the renderer stays readable.
Style goals: plain paper, one accent, no decoration that does not carry meaning.
"""

BASE_CSS = """
:root{
  --bg:#fcfbf8;--panel:#fff;--ink:#1c1c1c;--muted:#666;--faint:#8a8a8a;
  --line:#e4e0d6;--accent:#1f5f5b;--accent-soft:#e8f0ee;--code-bg:#12161c;
  --max:900px;--radius:10px;
  --sans:system-ui,-apple-system,"PingFang SC","Hiragino Sans GB","Noto Sans SC",sans-serif;
  --mono:"SFMono-Regular","Cascadia Code",Menlo,monospace;color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#141414;--panel:#1b1b1b;--ink:#e9e6df;--muted:#a3a09a;--faint:#7d7a75;
        --line:#2e2e2e;--accent:#7fb7ae;--accent-soft:#22302e;--code-bg:#0d1117;color-scheme:dark}
}
*{box-sizing:border-box}
input[type=checkbox]{accent-color:var(--accent)}
[hidden]{display:none!important}
html,body{max-width:100%;overflow-x:clip}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
     font-size:16px;line-height:1.7;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--accent) 30%,transparent)}
a:hover{border-bottom-color:var(--accent)}
.wrap{max-width:var(--max);margin:0 auto;padding:0 24px}
code,kbd{font-family:var(--mono);font-size:.9em}
:not(pre)>code{background:var(--accent-soft);padding:1px 5px;border-radius:4px}

/* header */
header.site{padding:44px 0 28px;border-bottom:1px solid var(--line)}
.eyebrow{margin:0 0 8px;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
h1{margin:0 0 10px;font-size:clamp(28px,4.4vw,40px);line-height:1.2;letter-spacing:-.01em}
.promise{margin:0;max-width:46em;color:var(--muted)}
.meta-row{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:12px;font-size:13px;color:var(--muted)}
.summary{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:18px;font-size:13px;color:var(--muted)}
.summary b{color:var(--ink);font-weight:600}

/* progress */
.progress-card{margin:22px 0 0;font-size:13px;color:var(--muted)}
.progress-head{display:flex;flex-wrap:wrap;gap:4px 12px;justify-content:space-between}
.bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:var(--accent);width:0;transition:width .3s}

/* sections */
main{padding:28px 0 56px}
section{margin:0 0 40px}
h2.sec{margin:0 0 14px;font-size:20px;line-height:1.3}
h2.sec span{font-weight:400;color:var(--faint);font-size:13px;margin-left:8px}
.lead{color:var(--muted);margin:0 0 16px}

/* notes */
.search{width:100%;margin:0 0 14px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;
        background:var(--panel);color:var(--ink);font:inherit;font-size:14px}
.search:focus{outline:2px solid color-mix(in srgb,var(--accent) 35%,transparent);outline-offset:1px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.note-card{border:1px solid var(--line);border-radius:var(--radius);padding:16px;background:var(--panel);
           display:flex;flex-direction:column;gap:8px}
.note-card[hidden]{display:none}
.note-card .num{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.08em}
.note-card h3{margin:0;font-size:16px;line-height:1.45}
.note-card h3 a{border-bottom:0}
.note-card .goal{margin:0;font-size:14px;color:var(--muted);flex:1}
.note-card .tags{display:flex;flex-wrap:wrap;gap:6px;font-size:11px;color:var(--muted)}
.note-card .tags span{background:var(--accent-soft);border-radius:4px;padding:1px 7px}
.note-card .path{margin:0;font-family:var(--mono);font-size:11px;color:var(--faint);word-break:break-all}
.note-card .check{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}

/* videos */
.video-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.video-card{border:1px solid var(--line);border-radius:var(--radius);padding:14px;background:var(--panel)}
.video-head h3{margin:0 0 3px;font-size:15px;line-height:1.45}
.video-meta{margin:0 0 10px;font-size:12px;color:var(--muted)}
.video-frame{position:relative;aspect-ratio:16/9;background:var(--code-bg);border-radius:8px;overflow:hidden}
.video-frame iframe{width:100%;height:100%;border:0}
.video-load{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;
            background:var(--code-bg);color:#e8e3d8;border:0;cursor:pointer;font:inherit;font-size:13px}
.video-load:hover{color:#fff}
.video-play{display:inline-flex;width:30px;height:30px;align-items:center;justify-content:center;
            border:1px solid rgba(255,255,255,.35);border-radius:50%;font-size:11px}
.video-why{margin:8px 0 0;font-size:12px;color:var(--muted)}

/* practice, review, glossary */
.practice{border:1px solid var(--line);border-radius:var(--radius);padding:18px;background:var(--panel)}
.practice h3{margin:0 0 6px;font-size:17px}
.practice ol{margin:12px 0 0;padding-left:20px}
.practice li{margin:9px 0}
.practice .check{color:var(--accent);font-size:13px}
.review-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.review-card{border:1px solid var(--line);border-radius:var(--radius);padding:14px;background:var(--panel)}
.review-card .front{margin:0 0 6px;font-weight:600}
.review-card .back{margin:0;font-size:14px;color:var(--muted)}
.review-card .back[hidden]{display:none}
.review-actions{display:flex;gap:8px;margin-top:10px}
.review-actions button{font:inherit;font-size:12px;padding:4px 10px;border:1px solid var(--line);
                       border-radius:6px;background:var(--panel);color:var(--ink);cursor:pointer}
.review-actions button:hover{border-color:var(--accent)}
.review-due{font-size:12px;color:var(--faint);margin-left:auto}
.glossary{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px 20px}
.glossary div{font-size:14px}
.glossary b{font-weight:600}
.list-plain{margin:0;padding-left:20px}
.list-plain li{margin:6px 0}

/* note page */
.note-head{padding:36px 0 22px;border-bottom:1px solid var(--line)}
.crumbs{font-size:12px;color:var(--faint);margin-bottom:10px}
.crumbs a{border-bottom:0}
.note-goal{margin:8px 0 0;color:var(--muted)}
.layout{display:grid;grid-template-columns:190px minmax(0,1fr);gap:36px;padding:28px 0 56px;align-items:start}
.toc{position:sticky;top:20px;font-size:13px;border-left:2px solid var(--line);padding-left:12px}
.toc p{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}
.toc a{display:block;padding:2px 0;color:var(--muted);border:0;line-height:1.45}
.toc a.lv3{padding-left:10px;font-size:12px}
.toc a:hover,.toc a.active{color:var(--accent)}
article.note{max-width:720px;min-width:0}
article.note h2{margin:34px 0 10px;font-size:22px;line-height:1.35}
article.note h3{margin:24px 0 8px;font-size:17px}
article.note p{margin:12px 0}
article.note ul,article.note ol{padding-left:22px;margin:12px 0}
article.note li{margin:4px 0}
article.note blockquote{margin:16px 0;padding:10px 14px;border-left:3px solid var(--line);color:var(--muted)}
article.note .callout{border:1px solid var(--line);border-left:3px solid var(--accent);
                      border-radius:8px;padding:12px 14px;margin:18px 0;background:var(--panel)}
article.note .callout-warning,article.note .callout-caution{border-left-color:#b4441f}
article.note .callout > p:first-child{margin-top:0}
article.note .callout > p:last-child{margin-bottom:0}
article.note .table-wrap{overflow-x:auto;margin:18px 0}
article.note table{border-collapse:collapse;width:100%;font-size:14px}
article.note th,article.note td{border:1px solid var(--line);padding:7px 10px;vertical-align:top}
article.note th{background:var(--accent-soft);font-weight:600;text-align:left}
article.note hr{border:0;border-top:1px solid var(--line);margin:28px 0}
article.note img{max-width:100%;border-radius:8px}
article.note .hl{background:var(--code-bg);border-radius:8px;padding:14px 16px;overflow:auto;
                 font-size:13px;line-height:1.55;margin:16px 0}
article.note .hl code{background:none;padding:0;color:#e6edf3;font-size:inherit}
article.note .hl[data-lang]::before{content:attr(data-lang);display:block;margin-bottom:6px;
                 font-family:var(--mono);font-size:11px;color:#8b949e;text-transform:lowercase}

/* quiz */
.quiz{border:1px solid var(--line);border-radius:var(--radius);padding:16px;margin:26px 0;background:var(--panel)}
.quiz h2{margin:0 0 6px;font-size:18px}
.quiz-status{margin:0 0 10px;font-size:12px;color:var(--faint)}
.quiz-item{border-top:1px solid var(--line);padding:12px 0}
.quiz-item:first-of-type{border-top:0}
.quiz-q{margin:0 0 8px;font-weight:600}
.quiz-option{display:block;width:100%;text-align:left;margin:5px 0;padding:8px 10px;font:inherit;font-size:14px;
             background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);cursor:pointer}
.quiz-option:hover{border-color:var(--accent)}
.quiz-option.right{border-color:#4f8a5b;background:color-mix(in srgb,#4f8a5b 12%,transparent)}
.quiz-option.wrong{border-color:#b4441f;background:color-mix(in srgb,#b4441f 10%,transparent)}
.quiz-why{margin:6px 0 0;font-size:13px;color:#b4441f}
.quiz-explain{display:none;margin:6px 0 0;font-size:13px;color:var(--muted)}
.quiz-explain.show{display:block}

.pager{display:flex;justify-content:space-between;gap:16px;margin-top:28px;padding-top:16px;
       border-top:1px solid var(--line);font-size:13px}
.sources{font-size:13px;color:var(--muted)}
footer.site{border-top:1px solid var(--line);padding:20px 0 40px;font-size:12px;color:var(--faint)}

@media(max-width:820px){
  .layout{grid-template-columns:1fr}
  .toc{position:static;border-left:0;padding-left:0;display:flex;flex-wrap:wrap;gap:4px 12px}
  .toc p{width:100%}
  .toc a.lv3{display:none}
}
@media(max-width:560px){
  .wrap{padding:0 18px}
  header.site{padding:30px 0 22px}
  h1{font-size:28px}
  .grid,.video-grid,.review-grid{grid-template-columns:1fr}
}
@media print{
  header.site,footer.site,.toc,.pager,.quiz,.video-grid,.progress-card,.search{display:none}
  body{background:#fff;color:#000}
  article.note{max-width:none}
  a{color:#000;border-bottom:0}
}
"""

APP_JS = """
(function(){
  var key = 'ls-series:' + (document.body.dataset.series || 'series');
  var noteId = document.body.dataset.noteId || '';
  var store = {};
  try { store = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (e) { store = {}; }
  store.done = store.done || {};
  store.quiz = store.quiz || {};
  store.review = store.review || {};
  function save(){ try { localStorage.setItem(key, JSON.stringify(store)); } catch(e){} }
  function days(n){ return n * 86400000; }
  function today(){ return new Date().toISOString().slice(0,10); }

  // progress + continue
  function renderProgress(){
    var boxes = document.querySelectorAll('[data-note-check]');
    var done = 0;
    boxes.forEach(function(box){
      box.checked = !!store.done[box.dataset.noteCheck];
      if (box.checked) done++;
    });
    var total = boxes.length;
    var bar = document.querySelector('[data-progress-bar]');
    var label = document.querySelector('[data-progress-label]');
    if (bar) bar.style.width = (total ? Math.round(done / total * 100) : 0) + '%';
    if (label) label.textContent = done + ' / ' + total + ' 篇';
    var cont = document.querySelector('[data-continue]');
    if (cont && store.last && store.last.id) {
      cont.hidden = false;
      cont.querySelector('a').href = 'notes/' + store.last.id;
      cont.querySelector('a').textContent = store.last.title || store.last.id;
    }
  }
  document.querySelectorAll('[data-note-check]').forEach(function(box){
    box.addEventListener('change', function(){
      store.done[box.dataset.noteCheck] = box.checked; save(); renderProgress();
    });
  });

  // remember last opened note
  if (noteId) {
    store.last = { id: document.body.dataset.noteHref || '', title: document.title.split(' · ')[0] };
    save();
  }
  renderProgress();

  // search
  var search = document.querySelector('[data-search]');
  if (search) {
    search.addEventListener('input', function(){
      var q = search.value.trim().toLowerCase();
      document.querySelectorAll('[data-note-card]').forEach(function(card){
        card.hidden = q && card.dataset.search.indexOf(q) === -1;
      });
    });
  }

  // video facade
  document.querySelectorAll('.video-frame[data-embed]').forEach(function(frame){
    var button = frame.querySelector('.video-load');
    if (!button) return;
    button.addEventListener('click', function(){
      var iframe = document.createElement('iframe');
      iframe.src = frame.dataset.embed;
      iframe.title = frame.dataset.title || 'video';
      iframe.allow = 'accelerometer; encrypted-media; picture-in-picture';
      iframe.referrerPolicy = 'no-referrer';
      iframe.setAttribute('allowfullscreen','');
      frame.innerHTML = ''; frame.appendChild(iframe);
    });
  });

  // review scheduling (1 / 3 / 7 days)
  var intervals = [1, 3, 7];
  function reviewCardState(card){
    var id = card.dataset.reviewId;
    return store.review[id] || { stage: 0, due: today() };
  }
  function renderReview(){
    var due = 0;
    document.querySelectorAll('.review-card').forEach(function(card){
      var state = reviewCardState(card);
      var label = card.querySelector('[data-review-due]');
      var isDue = state.due <= today();
      if (isDue) due++;
      if (label) label.textContent = isDue ? '今天到期' : ('下次 ' + state.due);
      card.dataset.stage = state.stage;
      card.dataset.due = state.due;
    });
    var badge = document.querySelector('[data-review-count]');
    if (badge) badge.textContent = due ? ('今天到期 ' + due + ' 张') : '今天没有到期卡';
  }
  document.querySelectorAll('.review-card').forEach(function(card){
    card.querySelector('.review-show').addEventListener('click', function(){
      var back = card.querySelector('.back');
      if (back) back.hidden = !back.hidden;
    });
    card.querySelectorAll('[data-grade]').forEach(function(btn){
      btn.addEventListener('click', function(){
        var id = card.dataset.reviewId;
        var state = reviewCardState(card);
        var remembered = btn.dataset.grade === 'ok';
        var stage = remembered ? Math.min(state.stage + 1, intervals.length) : 0;
        var wait = intervals[Math.min(stage, intervals.length - 1)];
        store.review[id] = { stage: stage, due: new Date(Date.now() + days(wait)).toISOString().slice(0,10) };
        save(); renderReview();
        var back = card.querySelector('.back'); if (back) back.hidden = true;
      });
    });
  });
  renderReview();

  // quiz with persistence
  var quizStore = noteId ? (store.quiz[noteId] || {}) : {};
  function saveQuiz(){ if (noteId) { store.quiz[noteId] = quizStore; save(); } }
  function quizSummary(){
    var items = document.querySelectorAll('.quiz-item');
    if (!items.length) return;
    var answered = 0, correct = 0;
    items.forEach(function(item){
      var saved = quizStore[item.dataset.qid];
      if (saved !== undefined) {
        answered++;
        if (saved === Number(item.dataset.answer)) correct++;
      }
    });
    var status = document.querySelector('[data-quiz-status]');
    if (status) status.textContent = answered ? ('上次答对 ' + correct + ' / ' + items.length) : '尚未作答';
  }
  document.querySelectorAll('.quiz-item').forEach(function(item){
    var answer = Number(item.dataset.answer);
    var options = Array.from(item.querySelectorAll('.quiz-option'));
    var explain = item.querySelector('.quiz-explain');
    var whyBox = item.querySelector('.quiz-why');
    function paint(chosen){
      options.forEach(function(other){ other.classList.remove('right','wrong'); });
      if (chosen === undefined || chosen === null) return;
      options.forEach(function(other, index){
        if (index === chosen) other.classList.add(index === answer ? 'right' : 'wrong');
      });
      if (chosen !== answer) options[answer].classList.add('right');
      if (explain) explain.classList.add('show');
      if (whyBox) {
        // 错选时就地说明这个选项错在哪；选项没写理由就保持隐藏。
        var reasons = [];
        try { reasons = JSON.parse(item.dataset.why || '[]'); } catch (err) { reasons = []; }
        var reason = chosen !== answer ? (reasons[chosen] || '') : '';
        whyBox.hidden = !reason;
        whyBox.textContent = reason ? ('这个选项为什么不对：' + reason) : '';
      }
    }
    var saved = quizStore[item.dataset.qid];
    if (saved !== undefined) paint(saved);
    options.forEach(function(button, index){
      button.addEventListener('click', function(){
        quizStore[item.dataset.qid] = index;
        saveQuiz(); paint(index); quizSummary();
      });
    });
  });
  quizSummary();

  // toc highlight
  var tocLinks = Array.from(document.querySelectorAll('.toc a[href^="#"]'));
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var map = {};
    tocLinks.forEach(function(link){ map[link.getAttribute('href').slice(1)] = link; });
    var observer = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (!entry.isIntersecting) return;
        tocLinks.forEach(function(l){ l.classList.remove('active'); });
        var link = map[entry.target.id]; if (link) link.classList.add('active');
      });
    }, { rootMargin: '-15% 0px -75% 0px' });
    Object.keys(map).forEach(function(id){
      var el = document.getElementById(id); if (el) observer.observe(el);
    });
  }
})();
"""
