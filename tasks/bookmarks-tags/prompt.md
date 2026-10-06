Add tags to bookmarks, through every layer of this app. `README.md` describes the existing modules.

## Rules for tags

A bookmark has `tags`, an array of strings. `normalizeBookmark` in `src/schema.js` cleans them:

- A missing `tags` field means `[]`. Anything else that is not an array is a `ValidationError` with `field` set to `'tags'`.
- Each tag is trimmed and lowercased. Tags that are empty after trimming are dropped. Duplicates are removed, keeping the first.
- After that, every tag must be 1 to 20 characters from `a`–`z`, `0`–`9` and `-`, and there can be at most 5 tags. Otherwise it is a `ValidationError` with `field` set to `'tags'`.

## Changes by module

- **`src/schema.js`**: `normalizeBookmark` returns `tags` as well, following the rules above.
- **`src/store.js`**: `add` accepts `tags`. `update` replaces the tags when `changes.tags` is given and keeps the existing ones when it is not.
- **`src/storage.js`**: the saved version becomes `2`. Data saved as version 1 still loads, with `tags: []` on every bookmark, and is written back as version 2.
- **`src/query.js`**:
  - `search` also matches a bookmark when the text is contained in one of its tags.
  - New `filterByTag(bookmarks, tag)` returns the bookmarks that have exactly that tag. The `tag` argument is trimmed and lowercased first.
  - New `allTags(bookmarks)` returns `[{ tag, count }]` for every tag in use, ordered by `count` (highest first) and then by `tag` (A to Z).
- **`src/exchange.js`**: `exportJson` writes `version: 2` and includes `tags` on every item. `importJson` accepts version 1 files (their items get `tags: []`) and version 2 files, and still rejects any other version.
- **`src/view.js`**: inside each `<li>`, after the link, every tag is rendered as `<span class="tag">name</span>` in stored order, with nothing between the elements. A bookmark without tags renders exactly as it does now.

No dependencies. Update the existing tests where the new `tags` field changes what they expect; `npm test` must pass.
