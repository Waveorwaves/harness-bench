Build a small Markdown preview page in this directory. Use plain JavaScript (ES modules) with no dependencies and no build step.

## Files

- `src/markdown.js` exports `render(markdown)`, which takes a string and returns an HTML string.
- `index.html` contains `<textarea id="source">` and an element with `id="preview"`, and loads `src/main.js` with `<script type="module">`.
- `src/main.js` imports `render` from `./markdown.js` and shows the rendered textarea content in `#preview`, updating on every input.

## What `render` supports

Treat `\r\n` as `\n`. Outside code blocks, ignore leading and trailing spaces on every line.

Blocks are separated by one or more blank lines. Render each block as below and join the results with a single `\n`. Empty or whitespace-only input gives an empty string.

| Block | Rule | Output |
|---|---|---|
| Heading | a one-line block starting with one to three `#` and then a space | `<h1>…</h1>` to `<h3>…</h3>` |
| Code block | starts at a line beginning with three backticks (anything after them on that line is ignored) and ends at the next line that is exactly three backticks | `<pre><code>…</code></pre>` |
| List | every line of the block starts with `- ` | `<ul><li>…</li><li>…</li></ul>` |
| Paragraph | anything else; its lines are joined with one space | `<p>…</p>` |

Inside a code block, keep the lines exactly as written (including indentation and blank lines), joined with `\n`, and apply no inline formatting.

Inline formatting, applied in headings, list items and paragraphs:

| Markdown | Output |
|---|---|
| `` `text` `` | `<code>text</code>`, with no other formatting inside |
| `**text**` | `<strong>text</strong>` |
| `*text*` | `<em>text</em>` |
| `[text](url)` | `<a href="url">text</a>` |

- The URL of a link runs up to the first `)`. Create the link only if the URL starts with `http://`, `https://`, `mailto:`, `/` or `#`. Otherwise output the original Markdown as plain text.
- A marker with no matching closing marker is plain text.
- Nested inline formatting is not required.
- Everywhere, including code and link URLs, replace `&`, `<`, `>` and `"` in the text with `&amp;`, `&lt;`, `&gt;` and `&quot;`.

Produce exactly the tags shown, with no extra attributes or whitespace.
