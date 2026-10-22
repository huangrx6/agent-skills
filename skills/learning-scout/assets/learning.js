(() => {
  const body = document.body;
  const planId = body.dataset.planId || "default";
  const storageKey = `learning-scout:${planId}`;
  const boxes = Array.from(document.querySelectorAll("input[data-progress-key]"));
  const keys = Array.from(new Set(boxes.map((box) => box.dataset.progressKey)));
  const total = keys.length;
  const countEl = document.getElementById("progress-count");
  const barEl = document.getElementById("progress-bar");
  let done = new Set();

  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (Array.isArray(saved)) done = new Set(saved.filter((key) => keys.includes(key)));
  } catch (_error) {
    done = new Set();
  }

  const paint = () => {
    boxes.forEach((box) => { box.checked = done.has(box.dataset.progressKey); });
    if (countEl) countEl.textContent = `${done.size} / ${total}`;
    if (barEl) barEl.style.width = total ? `${(done.size / total) * 100}%` : "0%";
  };

  const save = () => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(Array.from(done)));
    } catch (_error) {
      /* Private mode or a full quota: progress still works for this page view. */
    }
  };

  boxes.forEach((box) => {
    box.addEventListener("change", () => {
      const key = box.dataset.progressKey;
      if (box.checked) done.add(key); else done.delete(key);
      save();
      paint();
    });
  });

  paint();

  const filters = Array.from(document.querySelectorAll("[data-filter]"));
  const shelfCards = Array.from(document.querySelectorAll("#shelf-grid .resource-card"));

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.filter || "all";
      filters.forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", active ? "true" : "false");
      });
      shelfCards.forEach((card) => {
        card.hidden = filter !== "all" && card.dataset.format !== filter;
      });
    });
  });

  const revealables = Array.from(document.querySelectorAll(".reveal"));
  if (!("IntersectionObserver" in window) ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    revealables.forEach((node) => node.classList.add("is-visible"));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
    revealables.forEach((node) => observer.observe(node));
  }

  window.addEventListener("beforeprint", () => {
    revealables.forEach((node) => node.classList.add("is-visible"));
  });
})();
