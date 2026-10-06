// Tab widgets. See README.md.

export function initTabs(root) {
  const tabs = [...root.querySelectorAll('.tab')];
  const panels = [...root.querySelectorAll('.panel')];

  function select(tab) {
    tabs.forEach((other) => other.classList.toggle('active', other === tab));
    panels.forEach((panel) => panel.classList.toggle('open', panel.id === tab.dataset.panel));
  }

  tabs.forEach((tab) => tab.addEventListener('click', () => select(tab)));
}

document.querySelectorAll('.tabs').forEach(initTabs);
