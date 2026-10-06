// Tab widgets. See README.md.

export function initTabs(root) {
  const tabList = root.querySelector('.tab-list');
  const tabs = [...root.querySelectorAll('.tab')];
  const panels = [...root.querySelectorAll('.panel')];

  // Set up ARIA roles and initial attributes
  tabList.setAttribute('role', 'tablist');

  tabs.forEach((tab, index) => {
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', tab.dataset.panel);

    const isActive = tab.classList.contains('active');
    // Set initial aria-selected and tabindex: only the active tab should be in tab order
    tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    tab.setAttribute('tabindex', isActive ? '0' : '-1');
  });

  panels.forEach((panel) => {
    panel.setAttribute('role', 'tabpanel');

    // Find the corresponding tab for this panel
    const tab = tabs.find((t) => t.dataset.panel === panel.id);
    if (tab && tab.id) {
      panel.setAttribute('aria-labelledby', tab.id);
    }

    panel.setAttribute('tabindex', '0');

    // Set hidden attribute for non-open panels
    if (!panel.classList.contains('open')) {
      panel.setAttribute('hidden', '');
    }
  });

  function select(tab) {
    tabs.forEach((other) => {
      other.classList.toggle('active', other === tab);
      other.setAttribute('aria-selected', other === tab ? 'true' : 'false');
      other.setAttribute('tabindex', other === tab ? '0' : '-1');
    });

    panels.forEach((panel) => {
      const isOpen = panel.id === tab.dataset.panel;
      panel.classList.toggle('open', isOpen);
      if (isOpen) {
        panel.removeAttribute('hidden');
      } else {
        panel.setAttribute('hidden', '');
      }
    });
  }

  // Handle click events
  tabs.forEach((tab) => tab.addEventListener('click', () => select(tab)));

  // Handle keyboard events
  tabs.forEach((tab, index) => {
    tab.addEventListener('keydown', (e) => {
      let targetIndex = index;

      if (e.key === 'ArrowRight') {
        e.preventDefault();
        targetIndex = (index + 1) % tabs.length;
        select(tabs[targetIndex]);
        tabs[targetIndex].focus();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        targetIndex = (index - 1 + tabs.length) % tabs.length;
        select(tabs[targetIndex]);
        tabs[targetIndex].focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        select(tabs[0]);
        tabs[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        select(tabs[tabs.length - 1]);
        tabs[tabs.length - 1].focus();
      } else if (e.key === 'Tab') {
        // Allow Tab to move to the panel
        const selectedTab = tabs.find((t) => t.classList.contains('active'));
        if (selectedTab) {
          const panel = panels.find((p) => p.id === selectedTab.dataset.panel);
          if (panel) {
            e.preventDefault();
            panel.focus();
          }
        }
      }
    });
  });
}

document.querySelectorAll('.tabs').forEach(initTabs);
