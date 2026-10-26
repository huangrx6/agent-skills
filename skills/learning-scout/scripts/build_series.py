#!/usr/bin/env python3
"""Build a multi-note learning series: Markdown notes -> offline HTML workspace.

Input: plan.json (version 2) listing notes, videos, quizzes, practice and sources.
Output:
  <out>/index.html          hub: progress, note list, videos, practice, review
  <out>/notes/<slug>.html   one page per note, rendered from Markdown
  <out>/notes/<slug>.md     copy of the source note (portable, importable)
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import render_md
from series_theme import APP_JS, BASE_CSS

import check_notes

# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

VIDEO_HOSTS = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "youtu.be": "youtube",
    "bilibili.com": "bilibili",
    "www.bilibili.com": "bilibili",
    "player.bilibili.com": "bilibili",
    "vimeo.com": "vimeo",
    "www.vimeo.com": "vimeo",
}


# 选择题里出现「以上都/都不对」这类选项时，测的是排除法而不是理解；
# 正确项明显更长时，读者能靠长度猜。两条都只提示，不阻塞。
QUIZ_LAZY_OPTION_RE = re.compile(r"(以上都|都不对|全部正确|都不正确|以上均)")


class PlanError(ValueError):
    pass


def _text(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _attr(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _is_http(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "note"


def validate_plan(plan: object, base_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(plan, dict):
        return ["plan 必须是 JSON 对象"], warnings
    if plan.get("version") != 2:
        errors.append("version 必须为 2（多篇笔记系列）")
    for key in ("topic", "promise"):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            errors.append(f"缺少顶层字段 {key}")

    notes = plan.get("notes")
    if not isinstance(notes, list) or len(notes) < 2:
        errors.append("notes 至少需要 2 篇；单篇内容请直接用一段式笔记")
        notes = []

    seen_ids: set[str] = set()
    for index, note in enumerate(notes, start=1):
        where = f"notes[{index}]"
        if not isinstance(note, dict):
            errors.append(f"{where} 必须是对象")
            continue
        note_id = str(note.get("id") or "").strip()
        if not note_id:
            errors.append(f"{where} 缺少 id")
        elif note_id in seen_ids:
            errors.append(f"{where} 的 id 重复：{note_id}")
        else:
            seen_ids.add(note_id)

        title = note.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{where} 缺少 title")
        if not isinstance(note.get("goal"), str) or not note["goal"].strip():
            warnings.append(f"{where} 缺少 goal：读者不知道读完能做什么")

        rel = note.get("file")
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"{where} 缺少 file（指向 Markdown 原文）")
        else:
            path = (base_dir / rel).resolve()
            try:
                path.relative_to(base_dir.resolve())
            except ValueError:
                errors.append(f"{where}.file 越出计划目录：{rel}")
            else:
                if not path.is_file():
                    errors.append(f"{where}.file 不存在：{rel}")
                elif path.suffix.lower() != ".md":
                    errors.append(f"{where}.file 必须是 .md：{rel}")

        for video_index, video in enumerate(_as_list(note.get("videos")), start=1):
            vwhere = f"{where}.videos[{video_index}]"
            if not isinstance(video, dict):
                errors.append(f"{vwhere} 必须是对象")
                continue
            if not isinstance(video.get("title"), str) or not video["title"].strip():
                errors.append(f"{vwhere} 缺少 title")
            if not _is_http(video.get("url")):
                errors.append(f"{vwhere}.url 必须是 http(s) 链接")
            if not _as_dict(video).get("verified_at"):
                warnings.append(f"{vwhere} 缺少 verified_at（核验日期）")

        for quiz_index, item in enumerate(_as_list(note.get("quiz")), start=1):
            qwhere = f"{where}.quiz[{quiz_index}]"
            if not isinstance(item, dict):
                errors.append(f"{qwhere} 必须是对象")
                continue
            qtype = item.get("type") or "choice"
            if qtype not in ("choice", "short"):
                errors.append(f"{qwhere}.type 只能是 choice 或 short")
                continue
            if qtype == "short":
                # 回忆题：不给选项，自己写，再对照参考答案。识别题只证明眼熟。
                model = item.get("model_answer")
                if not isinstance(model, str) or not model.strip():
                    errors.append(f"{qwhere}.model_answer 必填：短答题没有参考答案就没法对照")
                if "options" in item or "answer" in item:
                    errors.append(f"{qwhere} 是 short 题，不要给 options/answer")
                continue
            options = _as_list(item.get("options"))
            if len(options) < 2:
                errors.append(f"{qwhere} 至少两个选项")
            answer = item.get("answer")
            if not isinstance(answer, int) or not 0 <= answer < max(len(options), 1):
                errors.append(f"{qwhere}.answer 必须是合法选项下标")
            if "why" in item:
                why = item.get("why")
                if not isinstance(why, list) or not all(isinstance(part, str) for part in why):
                    errors.append(f"{qwhere}.why 必须是字符串列表")
                elif len(why) != len(options):
                    errors.append(f"{qwhere}.why 要与 options 一一对应（{len(why)} 条理由 / {len(options)} 个选项）")
            joined = " ".join(str(option) for option in options)
            if QUIZ_LAZY_OPTION_RE.search(joined):
                warnings.append(f"{qwhere} 用了「以上都/都不对」这类选项：它测的是排除法，不是理解")
            if isinstance(answer, int) and 0 <= answer < len(options):
                correct = str(options[answer])
                others = [str(o) for i, o in enumerate(options) if i != answer]
                if others and len(correct) >= 20:
                    mean = sum(len(o) for o in others) / len(others)
                    if mean and len(correct) > 1.5 * mean:
                        warnings.append(f"{qwhere} 正确选项明显比其他选项长，读者能靠长度猜出来")

    for card_index, card in enumerate(_as_list(plan.get("review")), start=1):
        if not isinstance(card, dict):
            errors.append(f"review[{card_index}] 必须是对象")
            continue
        for key in ("front", "back"):
            if not isinstance(card.get(key), str) or not card[key].strip():
                errors.append(f"review[{card_index}] 缺少 {key}")

    sources = plan.get("sources")
    if not isinstance(sources, dict) or not sources.get("verified_at"):
        errors.append("sources.verified_at 必填：没有核验日期就不算完成")
    if not _as_list(plan.get("practice")) and not _as_dict(plan.get("practice")):
        warnings.append("整条系列没有 practice：至少安排一次动手任务")

    return errors, warnings


# --------------------------------------------------------------------------- #
# markdown -> html
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# video embeds
# --------------------------------------------------------------------------- #


def video_kind(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    return VIDEO_HOSTS.get(host)


def embed_url(url: str) -> str | None:
    kind = video_kind(url)
    parsed = urlparse(url)
    if kind == "youtube":
        if parsed.hostname == "youtu.be":
            vid = parsed.path.strip("/")
        elif "/shorts/" in parsed.path:
            vid = parsed.path.split("/shorts/")[1].split("/")[0]
        elif "/embed/" in parsed.path:
            vid = parsed.path.split("/embed/")[1].split("/")[0]
        else:
            vid = (parsed.query or "").split("v=")[-1].split("&")[0] if "v=" in (parsed.query or "") else ""
        return f"https://www.youtube-nocookie.com/embed/{vid}" if vid else None
    if kind == "bilibili":
        match = re.search(r"(BV[0-9A-Za-z]+)", url)
        if match:
            return f"https://player.bilibili.com/player.html?bvid={match.group(1)}&autoplay=0"
        if "player.bilibili.com" in (parsed.hostname or ""):
            return url
        return None
    if kind == "vimeo":
        vid = parsed.path.strip("/").split("/")[0]
        return f"https://player.vimeo.com/video/{vid}" if vid.isdigit() else None
    return None


def render_video(video: dict, index: int) -> str:
    title = _text(video.get("title"))
    url = _attr(video.get("url"))
    channel = _text(video.get("channel"))
    duration = _text(video.get("duration"))
    lang = _text(video.get("lang"))
    why = _text(video.get("why"))
    labels: list[str] = []
    if channel:
        labels.append(channel)
    if duration:
        labels.append(duration)
    if lang:
        labels.append(lang.upper())
    if video.get("paid"):
        labels.append("付费")
    if video.get("region"):
        labels.append(f"限 {_text(video.get('region'))}")
    meta = " · ".join(labels)
    embed = embed_url(str(video.get("url") or ""))
    player = ""
    if embed:
        player = (
            f'<div class="video-frame" data-embed="{_attr(embed)}" '
            f'data-title="{title}"><button type="button" class="video-load">'
            f'<span class="video-play" aria-hidden="true">▶</span><span>加载播放器（需联网）</span>'
            f"</button></div>"
        )
    else:
        player = '<p class="video-external">该平台不支持内嵌，请用下方链接打开。</p>'
    reason = f'<p class="video-why">{why}</p>' if why else ""
    return f"""<article class="video-card" id="video-{index}">
  <div class="video-head">
    <h3><a href="{url}" rel="noreferrer">{title}</a></h3>
    <p class="video-meta">{meta}</p>
  </div>
  {player}
  {reason}
</article>"""


# --------------------------------------------------------------------------- #
# page shell
# --------------------------------------------------------------------------- #

CSS = BASE_CSS + "\n" + render_md.CODE_CSS


def shell(title: str, body: str, series_key: str, note_id: str = "", note_href: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<title>{_text(title)}</title>
<style>{CSS}</style>
</head>
<body data-series="{_attr(series_key)}" data-note-id="{_attr(note_id)}" data-note-href="{_attr(note_href)}">
{body}
<script>{APP_JS}</script>
</body>
</html>
"""


def site_header(plan: dict) -> str:
    learner = _as_dict(plan.get("learner"))
    meta = []
    if learner.get("level"):
        meta.append(f"起点：{learner['level']}")
    if learner.get("time_per_day"):
        meta.append(f"投入：{learner['time_per_day']}")
    if plan.get("audience"):
        meta.append(str(plan["audience"]))
    meta_html = "".join(f"<span>{_text(item)}</span>" for item in meta)

    notes = _as_list(plan.get("notes"))
    minutes = sum(int(_as_dict(n).get("minutes") or 0) for n in notes)
    videos = sum(len(_as_list(_as_dict(n).get("videos"))) for n in notes)
    verified = _as_dict(plan.get("sources")).get("verified_at")
    summary = [f"<b>{len(notes)}</b> 篇", f"<b>{minutes}</b> 分钟", f"<b>{videos}</b> 个视频"]
    if verified:
        summary.append(f"核验于 {_text(verified)}")
    summary_html = "".join(f"<span>{item}</span>" for item in summary)

    return f"""<header class="site">
  <div class="wrap">
    <p class="eyebrow">Learning series</p>
    <h1>{_text(plan.get("topic"))}</h1>
    {f'<p class="promise">{_text(plan.get("promise"))}</p>' if plan.get("promise") else ""}
    <div class="meta-row">{meta_html}</div>
    <div class="summary">{summary_html}</div>
    <div class="progress-card">
      <div class="progress-head"><span>学习进度（保存在本机浏览器）</span><span data-progress-label>0 / {len(notes)} 篇</span></div>
      <div class="bar"><i data-progress-bar></i></div>
      <p class="progress-head" data-continue hidden style="margin-top:8px"><span>继续上次：<a href="#"></a></span></p>
    </div>
  </div>
</header>"""


def _render_list_section(title: str, items: list, note: str = "") -> str:
    if not items:
        return ""
    lis = []
    for item in items:
        if isinstance(item, dict):
            head = _text(item.get("title") or item.get("skill") or "")
            detail = _text(item.get("detail") or item.get("why") or "")
            lis.append(f"<li><strong>{head}</strong>{('：' + detail) if detail else ''}</li>")
        else:
            lis.append(f"<li>{_text(item)}</li>")
    subtitle = f"<span>{_text(note)}</span>" if note else ""
    return f"""<section>
  <h2 class="sec">{_text(title)}{subtitle}</h2>
  <ul class="list-plain">{"".join(lis)}</ul>
</section>"""


def render_index(plan: dict, notes_meta: list[dict], series_key: str) -> str:
    cards = []
    for note in notes_meta:
        videos = len(_as_list(note.get("videos")))
        tags = "".join(
            f"<span>{_text(tag)}</span>"
            for tag in [note.get("depth"), note.get("kind"), f"{note.get('minutes')} 分钟" if note.get("minutes") else ""]
            if tag
        )
        video_tag = f"<span>{videos} 个视频</span>" if videos else ""
        search_key = " ".join(
            str(value or "") for value in (note.get("title"), note.get("goal"), note.get("kind"))
        ).lower()
        cards.append(f"""<article class="note-card" data-note-card data-search="{_attr(search_key)}">
  <div class="num">NOTE {_text(note.get('id'))}</div>
  <h3><a href="notes/{_attr(note['slug'])}.html">{_text(note.get('title'))}</a></h3>
  <p class="goal">{_text(note.get('goal'))}</p>
  <div class="tags">{tags}{video_tag}</div>
  <p class="path">原文：notes/{_attr(note['slug'])}.md</p>
  <label class="check"><input type="checkbox" data-note-check="{_attr(note.get('id'))}" /> 标记已读完</label>
</article>""")

    all_videos: list[str] = []
    video_index = 0
    for note in notes_meta:
        for video in _as_list(note.get("videos")):
            video_index += 1
            all_videos.append(render_video(video, video_index))

    practice = _as_dict(plan.get("practice"))
    practice_html = ""
    if practice:
        steps = []
        for step_index, step in enumerate(_as_list(practice.get("steps")), start=1):
            step = _as_dict(step)
            parts = [f"<strong>{step_index}. {_text(step.get('do'))}</strong>"]
            if step.get("expect"):
                parts.append(f"<div>预期：{_text(step['expect'])}</div>")
            if step.get("check"):
                parts.append(f"<div class='check'>过关：{_text(step['check'])}</div>")
            steps.append(f"<li>{''.join(parts)}</li>")
        practice_html = f"""<section>
  <h2 class="sec">动手任务</h2>
  <div class="practice">
    <h3>{_text(practice.get('title'))}</h3>
    <p>{_text(practice.get('brief'))}</p>
    <ol>{''.join(steps)}</ol>
  </div>
</section>"""

    review_cards = []
    for card_index, card in enumerate(_as_list(plan.get("review")), start=1):
        card = _as_dict(card)
        source = f"<div class='sources'>依据：{_text(card.get('source'))}</div>" if card.get("source") else ""
        review_cards.append(f"""<div class="review-card" data-review-id="r{card_index}">
  <p class="front">{_text(card.get('front'))}</p>
  <p class="back" hidden>{_text(card.get('back'))}{source}</p>
  <div class="review-actions">
    <button type="button" class="review-show">显示答案</button>
    <button type="button" data-grade="again">忘了</button>
    <button type="button" data-grade="ok">记得</button>
    <span class="review-due" data-review-due></span>
  </div>
</div>""")
    review_html = (
        f"""<section>
  <h2 class="sec">复习卡 <span data-review-count></span></h2>
  <div class="review-grid">{''.join(review_cards)}</div>
</section>"""
        if review_cards
        else ""
    )

    glossary = [item for item in _as_list(plan.get("glossary")) if isinstance(item, dict)]
    glossary_html = (
        f"""<section>
  <h2 class="sec">术语表</h2>
  <div class="glossary">{''.join(f"<div><b>{_text(item.get('term'))}</b>：{_text(item.get('definition'))}</div>" for item in glossary)}</div>
</section>"""
        if glossary
        else ""
    )

    videos_html = (
        f"""<section>
  <h2 class="sec">视频</h2>
  <p class="lead">只核验标题、频道、时长与语言；未逐分钟观看的，不评价讲授质量。点击后才加载播放器。</p>
  <div class="video-grid">{''.join(all_videos)}</div>
</section>"""
        if all_videos
        else ""
    )

    sources = _as_dict(plan.get("sources"))
    sources_html = f"""<section>
  <h2 class="sec">来源与核验</h2>
  <p class="sources">链接核验日期：{_text(sources.get('verified_at'))}{('。' + _text(sources.get('note'))) if sources.get('note') else ''}</p>
</section>"""

    start = _as_dict(plan.get("start"))
    start_items = []
    for label, values in (("今天", _as_list(start.get("today"))), ("第一周", _as_list(start.get("week_one")))):
        for value in values:
            start_items.append(f"<li><strong>{label}</strong>：{_text(value)}</li>")
    start_html = (
        f"""<section>
  <h2 class="sec">从这里开始</h2>
  <ul class="list-plain">{''.join(start_items)}</ul>
</section>"""
        if start_items
        else ""
    )

    body = f"""{site_header(plan)}
<main class="wrap">
  {start_html}
  <section>
    <h2 class="sec">笔记<span>{len(cards)} 篇</span></h2>
    <input class="search" type="search" placeholder="搜索标题、目标或类型" data-search />
    <div class="grid">{''.join(cards)}</div>
  </section>
  {videos_html}
  {practice_html}
  {review_html}
  {_render_list_section("学完能做什么", _as_list(plan.get("outcomes")))}
  {_render_list_section("开始前最好具备", _as_list(plan.get("prerequisites")))}
  {glossary_html}
  {sources_html}
</main>
<footer class="site"><div class="wrap">离线可用；进度、答题与复习记录保存在本机浏览器，换设备或清缓存会丢失。 · <a href="print.html">打印 / 导出 PDF（全部篇目）</a></div></footer>"""
    return shell(str(plan.get("topic")), body, series_key)


def render_note_page(
    plan: dict,
    note: dict,
    content_html: str,
    toc: list[tuple[int, str, str]],
    prev_note: dict | None,
    next_note: dict | None,
    index: int,
    total: int,
    series_key: str,
) -> str:
    toc_html = ""
    if len(toc) >= 2:
        links = "".join(
            f'<a class="lv{level}" href="#{heading_id}">{_text(text)}</a>' for level, heading_id, text in toc
        )
        toc_html = f'<nav class="toc"><p>本页目录</p>{links}</nav>'

    videos = _as_list(note.get("videos"))
    video_html = ""
    if videos:
        cards = "".join(render_video(video, video_index) for video_index, video in enumerate(videos, start=1))
        video_html = f"""<section>
  <h2 class="sec">相关视频</h2>
  <div class="video-grid">{cards}</div>
</section>"""

    quiz_items = [item for item in _as_list(note.get("quiz")) if isinstance(item, dict)]
    quiz_html = ""
    if quiz_items:
        items = []
        for item_index, item in enumerate(quiz_items, start=1):
            if (item.get("type") or "choice") == "short":
                items.append(f"""<div class="quiz-item quiz-short" data-qid="q{item_index}">
  <p class="quiz-q">{item_index}. {_text(item.get('q'))}</p>
  <textarea class="quiz-input" rows="3" placeholder="先自己写下来，再对照参考答案"></textarea>
  <button type="button" class="quiz-reveal">对照参考答案</button>
  <div class="quiz-model" hidden>{_text(item.get('model_answer'))}</div>
  <p class="quiz-explain">{_text(item.get('explain'))}</p>
</div>""")
                continue
            options = "".join(
                f'<button type="button" class="quiz-option">{_text(option)}</button>'
                for option in _as_list(item.get("options"))
            )
            why = item.get("why") if isinstance(item.get("why"), list) else []
            why_attr = _attr(json.dumps(why, ensure_ascii=False)) if why else ""
            items.append(f"""<div class="quiz-item" data-qid="q{item_index}" data-answer="{int(item.get('answer', 0))}" data-why="{why_attr}">
  <p class="quiz-q">{item_index}. {_text(item.get('q'))}</p>
  {options}
  <p class="quiz-why" hidden></p>
  <p class="quiz-explain">{_text(item.get('explain'))}</p>
</div>""")
        quiz_html = f'<section class="quiz"><h2>自测</h2><p class="quiz-status" data-quiz-status></p>{"".join(items)}</section>'

    def pager_link(target: dict | None, label: str) -> str:
        if not target:
            return "<span></span>"
        return f'<a href="{_attr(target["slug"])}.html">{label}：{_text(target.get("title"))}</a>'

    meta_tags = "".join(
        f"<span>{_text(tag)}</span>"
        for tag in [note.get("depth"), note.get("kind"), f"{note.get('minutes')} 分钟" if note.get("minutes") else ""]
        if tag
    )
    body = f"""<header class="note-head"><div class="wrap">
  <div class="crumbs"><a href="../index.html">← 返回系列</a> · 第 {index} / {total} 篇</div>
  <h1>{_text(note.get('title'))}</h1>
  <p class="note-goal">{_text(note.get('goal'))}</p>
  <div class="meta-row">{meta_tags}</div>
</div></header>
<div class="wrap layout">
  {toc_html}
  <div>
    <article class="note">{content_html}</article>
    {video_html}
    {quiz_html}
    <div class="pager">{pager_link(prev_note, "上一篇")}{pager_link(next_note, "下一篇")}</div>
  </div>
</div>"""
    return shell(str(note.get("title")), body, series_key, str(note.get("id")), f"{note.get('slug')}.html")


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def copy_local_images(markdown: str, source_path: Path, notes_dir: Path) -> list[str]:
    """Copy relative images referenced by a note so the page works offline."""
    copied: list[str] = []
    root = notes_dir.resolve()
    for match in IMAGE_RE.finditer(markdown):
        rel = match.group(1)
        if rel.startswith(("http://", "https://", "data:", "#", "/")):
            continue
        src = (source_path.parent / rel).resolve()
        if not src.is_file():
            continue
        dst = (root / rel).resolve()
        try:
            dst.relative_to(root)
        except ValueError:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied.append(rel)
    return copied


PRINT_CSS = """
.print-cover{padding:40px 0 24px;border-bottom:1px solid var(--line);margin-bottom:24px}
.print-note{page-break-before:always;padding-top:8px}
.print-note:first-of-type{page-break-before:auto}
.print-note > h1{font-size:26px;margin:0 0 6px}
.print-note .goal{margin:0 0 18px;color:var(--muted)}
.print-note article{max-width:none}
.print-toc{font-size:14px;margin:18px 0 0;padding-left:20px}
.print-toc li{margin:4px 0}
@media print{
  a{color:#000;border:0}
  .print-cover{border-bottom:0}
  article.note .hl{background:#f7f6f2!important;border:1px solid #ddd}
  article.note .hl code,article.note .hl span{color:#1b1b1b!important}
  article.note .hl[data-lang]::before{color:#666}
}
"""

CSS = CSS + "\n" + PRINT_CSS


def render_print(plan: dict, rendered: list[tuple[dict, str]], series_key: str) -> str:
    toc = "".join(
        f'<li>{_text(note.get("title"))}{(" — " + _text(note.get("goal"))) if note.get("goal") else ""}</li>'
        for note, _ in rendered
    )
    body = [f"""<header class="print-cover">
  <p class="eyebrow">Learning series</p>
  <h1>{_text(plan.get("topic"))}</h1>
  <p class="promise">{_text(plan.get("promise"))}</p>
  <ol class="print-toc">{toc}</ol>
</header>"""]
    for note, content_html in rendered:
        body.append(f"""<section class="print-note">
  <h1>{_text(note.get("title"))}</h1>
  <p class="goal">{_text(note.get("goal"))}</p>
  <article class="note">{content_html}</article>
</section>""")
    body.append(
        f'<footer class="site"><div>核验日期：{_text(_as_dict(plan.get("sources")).get("verified_at"))}'
        f" · 共 {len(rendered)} 篇</div></footer>"
    )
    return shell(
        f"{plan.get('topic')} · 打印版",
        "\n".join(body),
        series_key,
    )


def load_plan(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError(f"JSON 解析失败：{exc}") from exc


def output_dir_for(plan: dict, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    slug = _slugify(str(plan.get("topic") or "learning"))
    return Path.home() / "Downloads" / "learning-scout" / f"{slug}-{date.today().isoformat()}"


def run_note_checks(plan: dict, base_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for note in _as_list(plan.get("notes")):
        note = _as_dict(note)
        rel = note.get("file")
        if not rel:
            continue
        path = (base_dir / str(rel)).resolve()
        if not path.is_file():
            continue
        note_errors, note_warnings = check_notes.check_note(path, str(note.get("kind") or ""), strict=False)
        errors.extend(note_errors)
        warnings.extend(note_warnings)
    return errors, warnings


def build(plan_path: Path, out: str | None, force: bool = False, check: bool = True) -> Path:
    plan = load_plan(plan_path)
    base_dir = plan_path.parent.resolve()
    errors, warnings = validate_plan(plan, base_dir)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        raise PlanError(f"{len(errors)} 个错误")

    if check:
        note_errors, note_warnings = run_note_checks(plan, base_dir)
        for warning in note_warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if note_errors:
            for error in note_errors:
                print(f"error: {error}", file=sys.stderr)
            raise PlanError("笔记未通过质量检查（用 --no-check 跳过）")

    series_key = _slugify(str(plan.get("topic")))
    notes = [note for note in _as_list(plan.get("notes")) if isinstance(note, dict)]
    for note in notes:
        note["slug"] = f"{note.get('id')}-{_slugify(str(note.get('title')))}"[:80]

    out_dir = output_dir_for(plan, out)
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise PlanError(f"输出目录已存在且非空：{out_dir}（加 --force 覆盖）")
    notes_dir = out_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[tuple[dict, str]] = []
    for index, note in enumerate(notes):
        source_path = (base_dir / str(note.get("file"))).resolve()
        markdown = source_path.read_text(encoding="utf-8")
        copy_local_images(markdown, source_path, notes_dir)
        content_html, toc = render_md.render(markdown)
        page = render_note_page(
            plan,
            note,
            content_html,
            toc,
            notes[index - 1] if index > 0 else None,
            notes[index + 1] if index + 1 < len(notes) else None,
            index + 1,
            len(notes),
            series_key,
        )
        (notes_dir / f"{note['slug']}.html").write_text(page, encoding="utf-8")
        shutil.copyfile(source_path, notes_dir / f"{note['slug']}.md")
        rendered.append((note, content_html))

    index_html = render_index(plan, notes, series_key)
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    (out_dir / "print.html").write_text(render_print(plan, rendered, series_key), encoding="utf-8")
    shutil.copyfile(plan_path, out_dir / "plan.json")

    report = out_dir / "README.md"
    report.write_text(
        "\n".join(
            [
                f"# {plan.get('topic')}",
                "",
                str(plan.get("promise") or ""),
                "",
                f"- 笔记：{len(notes)} 篇（`notes/*.md` 为原文，`notes/*.html` 为渲染页）",
                f"- 入口：`index.html`",
                f"- 核验日期：{_as_dict(plan.get('sources')).get('verified_at')}",
                "",
                "## 篇目",
                *[
                    f"{note.get('id')}. {note.get('title')} — {note.get('goal')}（{note.get('minutes') or '?'} 分钟） · notes/{note['slug']}.md"
                    for note in notes
                ],
                "",
                "Markdown 原文可直接导入任何支持 Markdown 的知识库；是否导入由使用者决定。",
            ]
        ),
        encoding="utf-8",
    )
    return out_dir


def _venv_candidates() -> list[Path]:
    """Where the optional renderer may live, newest convention first."""
    explicit = os.environ.get("LEARNING_SCOUT_VENV", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    home = Path(os.environ.get("AGENT_SKILLS_HOME", "~/.agent-skills")).expanduser()
    return [
        home / "data" / "learning-scout" / "venv",
        Path(__file__).resolve().parent.parent / ".venv",  # 旧版 skill 内 venv
    ]


def _ensure_engine() -> None:
    """Re-run with the project venv when the optional renderer is installed there."""
    if render_md.ENGINE != "fallback":
        return
    for venv in _venv_candidates():
        candidates = [venv / "bin" / "python", venv / "Scripts" / "python.exe"]
        venv_python = next((path for path in candidates if path.exists()), None)
        if venv_python and Path(sys.executable).resolve() != venv_python.resolve():
            os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    print(
        "note: 未找到 markdown-it-py，使用内置渲染器（嵌套列表会被拍平）；"
        "运行 sh scripts/setup.sh 可启用完整 Markdown。",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    _ensure_engine()
    parser = argparse.ArgumentParser(description="把多篇 Markdown 笔记构建成离线 HTML 学习系列")
    sub = parser.add_subparsers(dest="command", required=True)
    build_cmd = sub.add_parser("build", help="校验并构建 index.html 与 notes/*.html")
    build_cmd.add_argument("--input", required=True, help="plan.json 路径")
    build_cmd.add_argument("--out", help="输出目录（默认 ~/Downloads/learning-scout/<topic>-<date>）")
    build_cmd.add_argument("--force", action="store_true", help="覆盖已存在的非空输出目录")
    build_cmd.add_argument("--no-check", dest="check", action="store_false", help="跳过笔记质量检查")
    build_cmd.add_argument("--open", action="store_true", help="构建后打开 index.html")
    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            out_dir = build(Path(args.input).expanduser().resolve(), args.out, force=args.force, check=args.check)
        except PlanError as exc:
            print(f"\n构建失败：{exc}", file=sys.stderr)
            return 1
        print(f"输出：{out_dir}")
        print(f"入口：{out_dir / 'index.html'}")
        if args.open:
            import webbrowser

            webbrowser.open((out_dir / "index.html").as_uri())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
