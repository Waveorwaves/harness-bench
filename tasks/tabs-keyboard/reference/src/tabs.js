// Tab widgets. See README.md.

// A widget owns only the tabs and panels that are not inside a widget nested within it.
function own(root, selector) {
  return [...root.querySelectorAll(selector)].filter((element) => element.closest('.tabs') === root);
}

export function initTabs(root) {
  const list = own(root, '.tab-list')[0];
  const tabs = own(root, '.tab');
  const panels = own(root, '.panel');
  const panelOf = (tab) => panels.find((panel) => panel.id === tab.dataset.panel);

  function select(tab, focus = false) {
    for (const other of tabs) {
      const chosen = other === tab;
      other.classList.toggle('active', chosen);
      other.setAttribute('aria-selected', String(chosen));
      other.tabIndex = chosen ? 0 : -1;
    }
    for (const panel of panels) {
      const chosen = panel === panelOf(tab);
      panel.classList.toggle('open', chosen);
      panel.hidden = !chosen;
    }
    if (focus) tab.focus();
  }

  if (list) list.setAttribute('role', 'tablist');
  for (const tab of tabs) {
    const panel = panelOf(tab);
    tab.setAttribute('role', 'tab');
    if (panel) {
      tab.setAttribute('aria-controls', panel.id);
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', tab.id);
      panel.tabIndex = 0;
    }
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', (event) => {
      const index = tabs.indexOf(tab);
      const target = {
        ArrowRight: tabs[(index + 1) % tabs.length],
        ArrowLeft: tabs[(index - 1 + tabs.length) % tabs.length],
        Home: tabs[0],
        End: tabs[tabs.length - 1],
      }[event.key];
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      select(target, true);
    });
  }
  select(tabs.find((tab) => tab.classList.contains('active')) ?? tabs[0]);
}

document.querySelectorAll('.tabs').forEach(initTabs);
