(() => {
  const root = document.documentElement;
  root.classList.add("js");

  const pages = Array.from(document.querySelectorAll(".page"));
  const railLinks = Array.from(document.querySelectorAll(".page-rail a"));
  const current = document.getElementById("page-current");
  const bar = document.getElementById("page-bar");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const body = document.body;
  const planId = body.dataset.planId || "plan";
  const stageCount = Number(body.dataset.stageCount || 0);
  const storageKey = `learning-scout:${planId}`;
  const days = { 1: 1, 2: 3, 3: 7 };

  let frame = 0;
  let active = 0;
  let initialized = false;

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const pad = (value) => String(value).padStart(2, "0");
  const today = () => {
    const now = new Date();
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  };
  const addDays = (iso, amount) => {
    const date = new Date(`${iso}T12:00:00`);
    date.setDate(date.getDate() + amount);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  };

  function emptyState() {
    return { completed: [], quiz: {}, review: {}, lastPage: 1 };
  }

  function loadState() {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) return emptyState();
      const parsed = JSON.parse(raw);
      return {
        completed: Array.isArray(parsed.completed) ? parsed.completed : [],
        quiz: parsed.quiz && typeof parsed.quiz === "object" ? parsed.quiz : {},
        review: parsed.review && typeof parsed.review === "object" ? parsed.review : {},
        lastPage: Number.isFinite(parsed.lastPage) ? parsed.lastPage : 1,
      };
    } catch {
      return emptyState();
    }
  }

  const store = loadState();

  function saveState() {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(store));
    } catch {
      // File URLs can be read-only in some browsers; the page still works.
    }
  }

  function syncCompletion() {
    const done = new Set(store.completed);
    document.querySelectorAll("[data-complete-stage]").forEach((button) => {
      const stage = button.dataset.completeStage;
      const isDone = done.has(stage);
      button.classList.toggle("is-done", isDone);
      button.setAttribute("aria-pressed", String(isDone));
      button.textContent = isDone ? "已完成 · 再点取消" : "标记本章完成";
      const state = document.querySelector(`[data-complete-state="${CSS.escape(stage)}"]`);
      if (state) state.textContent = isDone ? "已记录 · 本机" : "未完成 · 记录在本机";
    });
    const counter = document.getElementById("done-count");
    if (counter) counter.textContent = `${pad(done.size)} / ${pad(stageCount)}`;
  }

  document.querySelectorAll("[data-complete-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      const stage = button.dataset.completeStage;
      const index = store.completed.indexOf(stage);
      if (index === -1) store.completed.push(stage);
      else store.completed.splice(index, 1);
      saveState();
      syncCompletion();
    });
  });

  function markQuiz(item, chosen) {
    const answer = Number(item.dataset.answer);
    const buttons = Array.from(item.querySelectorAll(".quiz-option"));
    const correct = chosen === answer;
    buttons.forEach((option, index) => {
      option.disabled = true;
      option.classList.toggle("is-correct", index === answer);
      option.classList.toggle("is-wrong", index === chosen && !correct);
    });
    const explain = item.querySelector(".quiz-explain");
    if (explain) {
      explain.hidden = false;
      let result = explain.querySelector(".quiz-result");
      if (!result) {
        result = document.createElement("b");
        result.className = "quiz-result";
        explain.prepend(result);
      }
      result.textContent = correct ? "答对了。" : "再看一次。";
      result.classList.toggle("is-ok", correct);
      result.classList.toggle("is-bad", !correct);
    }
    store.quiz[item.dataset.quizId] = {
      stage: item.dataset.stage,
      chosen,
      correct,
    };
    saveState();
    updateWeakSummary();
  }

  document.querySelectorAll(".quiz-item").forEach((item) => {
    const buttons = Array.from(item.querySelectorAll(".quiz-option"));
    buttons.forEach((option) => {
      option.addEventListener("click", () => {
        if (item.dataset.answered === "1") return;
        item.dataset.answered = "1";
        markQuiz(item, Number(option.dataset.index));
      });
    });
    const saved = store.quiz[item.dataset.quizId];
    if (saved && Number.isInteger(saved.chosen)) {
      item.dataset.answered = "1";
      markQuiz(item, saved.chosen);
    }
  });

  function updateWeakSummary() {
    const weak = document.getElementById("weak-count");
    if (!weak) return;
    const stages = new Set(
      Object.values(store.quiz)
        .filter((item) => item && item.correct === false)
        .map((item) => item.stage)
    );
    weak.textContent = `${stages.size} 个薄弱章节`;
  }

  function updateReviewSummary() {
    const dueCount = document.getElementById("review-due-count");
    if (!dueCount) return;
    const date = today();
    const cards = Array.from(document.querySelectorAll(".review-card"));
    const due = cards.filter((card) => {
      const saved = store.review[card.dataset.reviewId];
      return saved && saved.due && saved.due <= date;
    }).length;
    dueCount.textContent = due ? `${due} 张今天到期` : "今天没有到期卡片";
    const now = document.getElementById("review-today");
    if (now) now.textContent = date;
    cards.forEach((card) => {
      const saved = store.review[card.dataset.reviewId];
      const label = card.querySelector("[data-review-due]");
      if (label && saved && saved.due) {
        label.textContent = `下次 ${saved.due} · ${saved.days} 天`;
      }
    });
  }

  document.querySelectorAll(".review-card").forEach((card) => {
    const reveal = card.querySelector(".review-reveal");
    const back = card.querySelector(".review-back");
    const rating = card.querySelector(".review-rating");
    if (reveal) {
      reveal.addEventListener("click", () => {
        const open = card.classList.toggle("is-open");
        if (back) back.hidden = !open;
        if (rating) rating.hidden = !open;
        reveal.textContent = open ? "收起答案 " : "先回忆，再翻面 ";
        const symbol = document.createElement("span");
        symbol.setAttribute("aria-hidden", "true");
        symbol.textContent = open ? "↥" : "↻";
        reveal.appendChild(symbol);
      });
    }
    card.querySelectorAll("[data-rating]").forEach((button) => {
      button.addEventListener("click", () => {
        const rating = Number(button.dataset.rating);
        const interval = days[rating] || 1;
        const date = today();
        store.review[card.dataset.reviewId] = {
          rating,
          days: interval,
          due: addDays(date, interval),
          last: date,
        };
        const label = card.querySelector("[data-review-due]");
        if (label) label.textContent = `下次 ${store.review[card.dataset.reviewId].due} · ${interval} 天`;
        saveState();
        updateReviewSummary();
      });
    });
  });

  function updateResume() {
    const link = document.getElementById("resume-link");
    const label = document.getElementById("resume-label");
    if (!link || !label) return;
    if (store.lastPage > 1 && store.lastPage <= pages.length) {
      link.hidden = false;
      link.href = `#${pages[store.lastPage - 1].id}`;
      label.textContent = `第 ${store.lastPage} 页`;
    } else {
      link.hidden = true;
    }
  }

  function exportMarkdown() {
    const stageNames = new Map(
      Array.from(document.querySelectorAll(".page--work")).map((page) => [
        page.dataset.stage,
        page.dataset.stageName || page.dataset.stage,
      ])
    );
    const completed = store.completed
      .map((stage) => `- ${stageNames.get(stage) || stage}`)
      .join("\n") || "- 还没有标记完成的章节";

    const quizByStage = new Map();
    document.querySelectorAll(".quiz-item").forEach((item) => {
      const saved = store.quiz[item.dataset.quizId];
      if (!saved) return;
      const stage = item.dataset.stage;
      const row = quizByStage.get(stage) || { correct: 0, total: 0 };
      row.total += 1;
      if (saved.correct) row.correct += 1;
      quizByStage.set(stage, row);
    });
    const quizLines = Array.from(quizByStage.entries())
      .map(([stage, row]) => `- ${stageNames.get(stage) || stage}：${row.correct} / ${row.total}`)
      .join("\n") || "- 还没有做题";

    const weak = Array.from(quizByStage.entries())
      .filter(([, row]) => row.correct < row.total)
      .map(([stage]) => `- ${stageNames.get(stage) || stage}`)
      .join("\n") || "- 暂无（或者还没做题）";

    const reviewLines = Array.from(document.querySelectorAll(".review-card"))
      .map((card) => {
        const saved = store.review[card.dataset.reviewId];
        const front = card.querySelector(".review-front")?.textContent?.trim() || card.dataset.reviewId;
        return saved && saved.due ? `- ${saved.due} · ${front}` : `- 未安排 · ${front}`;
      })
      .join("\n") || "- 没有复习卡";

    const title = document.title.split(" · ")[0] || "学习记录";
    const markdown = `# ${title} · 学习记录\n\n生成时间：${today()}\n\n进度：${store.completed.length} / ${stageCount} 章\n\n## 已完成\n\n${completed}\n\n## 测验\n\n${quizLines}\n\n## 薄弱点\n\n${weak}\n\n## 复习队列\n\n${reviewLines}\n\n## 下一步\n\n打开原页面，继续完成未标记的章节；复习卡到期后再回来。\n`;
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${title.replace(/[\\/:*?"<>|]/g, "-")}-progress.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const exportButton = document.getElementById("export-progress");
  if (exportButton) exportButton.addEventListener("click", exportMarkdown);
  const resetButton = document.getElementById("reset-progress");
  if (resetButton) {
    resetButton.addEventListener("click", () => {
      if (!window.confirm("清空本机的完成记录、测验答案和复习安排？")) return;
      try {
        window.localStorage.removeItem(storageKey);
      } catch {
        // Ignore storage failures; reload still shows the reset view.
      }
      window.location.reload();
    });
  }

  function paint() {
    frame = 0;
    if (!pages.length) return;

    const vh = window.innerHeight || 1;
    let bestIndex = 0;
    let bestDistance = Infinity;

    pages.forEach((page, index) => {
      const rect = page.getBoundingClientRect();
      const distance = Math.abs(rect.top);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
      if (!reduceMotion) {
        const center = rect.top + rect.height / 2;
        const progress = clamp((vh / 2 - center) / vh, -1, 1);
        page.style.setProperty("--p", progress.toFixed(3));
      }
    });

    if (bestIndex !== active) {
      active = bestIndex;
      pages.forEach((page, index) => {
        page.classList.toggle("is-active", index === active);
      });

      const stage = pages[active].dataset.stage || "";
      railLinks.forEach((link) => {
        link.classList.toggle("is-active", Boolean(stage) && link.dataset.stage === stage);
      });
      if (initialized) {
        store.lastPage = active + 1;
        saveState();
        updateResume();
      }
    }

    if (current) current.textContent = `${pad(active + 1)} / ${pad(pages.length)}`;
    if (bar) bar.style.width = `${((active + 1) / pages.length) * 100}%`;
    initialized = true;
  }

  function schedule() {
    if (!frame) frame = window.requestAnimationFrame(paint);
  }

  function go(index) {
    const target = pages[clamp(index, 0, pages.length - 1)];
    if (!target) return;
    target.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "start",
    });
  }

  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);

  window.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    if (event.key === "PageDown") {
      event.preventDefault();
      go(active + 1);
    } else if (event.key === "PageUp") {
      event.preventDefault();
      go(active - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      go(0);
    } else if (event.key === "End") {
      event.preventDefault();
      go(pages.length - 1);
    }
  });

  railLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      const stage = link.dataset.stage;
      const page = pages.find(
        (item) => item.dataset.stage === stage && item.classList.contains("page--chapter")
      );
      if (page) {
        event.preventDefault();
        page.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
      }
    });
  });

  pages.forEach((page, index) => page.classList.toggle("is-active", index === 0));
  paint();
  syncCompletion();
  updateReviewSummary();
  updateWeakSummary();
  updateResume();
})();
