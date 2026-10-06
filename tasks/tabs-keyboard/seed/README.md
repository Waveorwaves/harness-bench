# Settings page

A static settings page with two tab widgets: the main settings tabs, and a billing-period switch inside the Billing panel. No build step; open `index.html` through any static server.

## How the tabs are built

Each widget is an element with class `tabs` containing:

- a `.tab-list` holding one `.tab` button per panel, each with `data-panel` naming its panel's id;
- one `.panel` per tab.

`src/tabs.js` exports `initTabs(root)` and calls it for every `.tabs` element on the page. The selected tab has the class `active` and its panel has the class `open`; the styles in `src/tabs.css` depend on those two classes.

## Keyboard and screen readers

The widgets should follow the standard tabs pattern, with a tab becoming selected as soon as it receives focus from the keyboard.

Roles and states:

- The `.tab-list` has `role="tablist"`.
- Every `.tab` has `role="tab"`, `aria-selected` set to `"true"` or `"false"`, and `aria-controls` set to its panel's id.
- Every `.panel` has `role="tabpanel"`, `aria-labelledby` set to its tab's id, and `tabindex="0"`.
- A panel that is not selected has the `hidden` attribute. The selected one does not.
- Only the selected tab is in the page's Tab order: it has `tabindex="0"` and the other tabs have `tabindex="-1"`.
- The classes `active` and `open` keep marking the selected tab and its panel.

Keys, while a tab has focus:

| Key | Result |
|---|---|
| Right arrow | focus and select the next tab; from the last tab, go to the first |
| Left arrow | focus and select the previous tab; from the first tab, go to the last |
| Home | focus and select the first tab |
| End | focus and select the last tab |
| Tab | leave the tab list: focus moves to the selected panel |

Clicking a tab selects it, as now.

Each `.tabs` widget works on its own. Using one must never change another, including when one widget sits inside a panel of another.
