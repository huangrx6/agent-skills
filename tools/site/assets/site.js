(() => {
  const header = document.querySelector('.site-header');
  const navToggle = document.querySelector('.nav-toggle');
  if (header && navToggle) {
    const closeNav = () => {
      header.dataset.navOpen = 'false';
      navToggle.setAttribute('aria-expanded', 'false');
    };
    navToggle.addEventListener('click', () => {
      const open = header.dataset.navOpen !== 'true';
      header.dataset.navOpen = String(open);
      navToggle.setAttribute('aria-expanded', String(open));
    });
    header.querySelectorAll('.site-nav a').forEach((link) => link.addEventListener('click', closeNav));
  }

  const root = document.documentElement;
  const themeToggle = document.querySelector('[data-theme-toggle]');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try {
        localStorage.setItem('agent-skills-theme', next);
      } catch (error) {}
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.content = next === 'dark' ? '#0f1012' : '#f5f3ee';
    });
  }

  const body = document.body;
  const sidebarToggle = document.querySelector('.sidebar-toggle');
  const backdrop = document.querySelector('.sidebar-backdrop');
  const setSidebar = (open) => {
    body.classList.toggle('sidebar-open', open);
    if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', String(open));
    if (backdrop) backdrop.hidden = !open;
  };
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => {
      setSidebar(!body.classList.contains('sidebar-open'));
    });
  }
  if (backdrop) backdrop.addEventListener('click', () => setSidebar(false));
  document.querySelectorAll('.docs-sidebar a').forEach((link) => {
    link.addEventListener('click', () => setSidebar(false));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setSidebar(false);
  });

  const copyText = async (text, button) => {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = '已复制';
    } catch (error) {
      button.textContent = '复制失败';
    }
    window.setTimeout(() => {
      button.textContent = '复制';
    }, 1600);
  };

  const bindCopy = (pre, button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const code = pre.querySelector('code');
      copyText((code || pre).innerText.trim(), button);
    });
  };

  document.querySelectorAll('pre').forEach((pre) => {
    if (pre.closest('.terminal')) return;
    if (pre.querySelector('.copy-btn')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'copy-btn';
    button.textContent = '复制';
    pre.appendChild(button);
    bindCopy(pre, button);
  });

  document.querySelectorAll('[data-copy-target]').forEach((button) => {
    const target = document.getElementById(button.dataset.copyTarget);
    if (target) bindCopy(target, button);
  });
})();
