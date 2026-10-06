Build a to-do list page in `index.html`, with plain HTML, CSS and JavaScript. No libraries and nothing loaded from the network; you may split it into several local files.

## What it does

- **Adding.** A form with `id="new-todo"` contains a text input. Typing a title and pressing Enter adds it to the end of the list, then empties the input and leaves it focused. Spaces around the title are removed, and a title that is empty after that adds nothing.
- **The list** is `<ul id="todos">`. Each to-do is an `<li>` containing, in this order: a checkbox, the title in `<span class="title">`, and a `<button class="delete">` whose `aria-label` is `Delete ` followed by the title.
- **Completing.** Ticking the checkbox marks the to-do as done: its `<li>` gets the class `done`. Unticking removes it.
- **Deleting.** The delete button removes its to-do.
- **Counter.** The element with `id="count"` shows how many to-dos are not done, as `0 left`, `1 left`, `2 left` and so on.
- **Filters.** Three buttons with `data-filter="all"`, `data-filter="active"` and `data-filter="done"` choose which to-dos are visible. The chosen button has `aria-pressed="true"` and the other two have `aria-pressed="false"`. The page starts on `all`.
- **Clear completed.** A button with `id="clear-done"` removes every done to-do. It is disabled when there are none.
- **Editing.** Double-clicking a title replaces it with a focused text input of class `edit` that holds the title. Enter saves the new title, with the spaces around it removed; if nothing is left, the to-do is deleted. Escape cancels and keeps the old title.
- **Remembering.** To-dos, with their done state and their order, are still there after the page is reloaded. The filter goes back to `all`.
- **Titles are text.** A title such as `<b>bold</b>` appears exactly as typed.
- The browser console shows no errors.

Make it pleasant to use: clear layout, readable type, visible focus.
