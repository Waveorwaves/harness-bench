# Bookmarks

A small bookmark manager. No dependencies; open `index.html` through any static server.

| Module | What it does |
|---|---|
| `src/schema.js` | `normalizeBookmark(input)` checks and cleans `{ url, title, createdAt }`. Problems throw a `ValidationError` whose `field` names the bad field. |
| `src/storage.js` | `serialize(state)` and `deserialize(text)` convert the saved state to and from JSON. The saved form carries a `version`; older versions are upgraded on load by the functions in `MIGRATIONS`. |
| `src/store.js` | `createStore(adapter)` keeps the bookmarks and saves after every change through `adapter.read()` and `adapter.write(text)`. It offers `add`, `update`, `remove` and `list`. |
| `src/query.js` | `search(bookmarks, text)` and `sortBy(bookmarks, order)`. |
| `src/exchange.js` | `exportJson(bookmarks)` and `importJson(text)` for moving bookmarks between browsers. The file carries its own `version`, separate from storage. |
| `src/view.js` | `renderList(bookmarks)` returns the list as an HTML string, with everything escaped. |

A stored bookmark looks like `{ id: 3, url: 'https://example.com/', title: 'Example', createdAt: '2026-03-01T09:30:00.000Z' }`.
