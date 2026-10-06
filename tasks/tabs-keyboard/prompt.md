An accessibility review of this settings page found that its tabs only work with a mouse. Keyboard users cannot move between tabs with the arrow keys, the Tab key stops on every tab instead of moving on to the content, and screen readers are told nothing about which tab is selected or which panel belongs to it.

`README.md` has a section "Keyboard and screen readers" that describes how the tabs are meant to behave. The code in `src/tabs.js` does none of it. Make the tabs behave as that section says.

Keep clicking working as it does now, and keep the existing ids and class names: the page's styles and other scripts rely on them.
