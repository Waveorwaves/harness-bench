// Hidden acceptance checks. Inputs are unseen; every expectation is stated in the prompt.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const checks = [];
const load = (file) => import(pathToFileURL(path.resolve(file)).href);

async function check(name, body) {
  try {
    await body();
    checks.push({ name, passed: true });
  } catch (error) {
    checks.push({ name, passed: false, detail: String(error?.message ?? error).slice(0, 400) });
  }
}

function renders(name, cases) {
  return check(name, async () => {
    const { render } = await load('src/markdown.js');
    for (const [markdown, html] of cases) assert.equal(render(markdown), html, JSON.stringify(markdown));
  });
}

const F = '```';

await renders('headings', [
  ['# One', '<h1>One</h1>'],
  ['## Two', '<h2>Two</h2>'],
  ['### Three', '<h3>Three</h3>'],
]);
await renders('four hashes or a missing space is a paragraph', [
  ['#### Four', '<p>#### Four</p>'],
  ['#Tight', '<p>#Tight</p>'],
]);
await renders('paragraph lines join with one space', [
  ['first line\nsecond line\nthird', '<p>first line second line third</p>'],
]);
await renders('blocks join with one newline', [
  ['# Title\n\nbody\n\n\n\nmore', '<h1>Title</h1>\n<p>body</p>\n<p>more</p>'],
]);
await renders('list', [
  ['- apples\n- pears\n- plums', '<ul><li>apples</li><li>pears</li><li>plums</li></ul>'],
]);
await renders('surrounding spaces on lines are ignored', [
  ['   ## Spaced   ', '<h2>Spaced</h2>'],
  ['  one  \n   two ', '<p>one two</p>'],
  ['  - a\n  - b  ', '<ul><li>a</li><li>b</li></ul>'],
]);
await renders('code block keeps lines, blank lines and indentation', [
  [`${F}\nif (a) {\n\n    b();\n}\n${F}`, '<pre><code>if (a) {\n\n    b();\n}</code></pre>'],
]);
await renders('code block ignores the info string and escapes without formatting', [
  [`${F}html\n<b>**x**</b> & "y"\n${F}`, '<pre><code>&lt;b&gt;**x**&lt;/b&gt; &amp; &quot;y&quot;</code></pre>'],
  [`before\n\n${F}\n- not a list\n${F}\n\nafter`, '<p>before</p>\n<pre><code>- not a list</code></pre>\n<p>after</p>'],
]);
await renders('bold and italic', [
  ['a **bold** move', '<p>a <strong>bold</strong> move</p>'],
  ['an *italic* word', '<p>an <em>italic</em> word</p>'],
  ['**one** and *two*', '<p><strong>one</strong> and <em>two</em></p>'],
]);
await renders('inline code has no formatting inside', [
  ['use `**kwargs` here', '<p>use <code>**kwargs</code> here</p>'],
  ['`a < b` is *true*', '<p><code>a &lt; b</code> is <em>true</em></p>'],
]);
await renders('links', [
  ['see [the docs](https://example.com/a?b=1)', '<p>see <a href="https://example.com/a?b=1">the docs</a></p>'],
  ['[home](/) and [top](#top)', '<p><a href="/">home</a> and <a href="#top">top</a></p>'],
  ['- [mail](mailto:me@example.com)', '<ul><li><a href="mailto:me@example.com">mail</a></li></ul>'],
  ['## [plain](http://example.com)', '<h2><a href="http://example.com">plain</a></h2>'],
]);
await renders('unsafe link stays plain text', [
  ['[click](javascript:steal)', '<p>[click](javascript:steal)</p>'],
  ['[x](data:text/html,hi)', '<p>[x](data:text/html,hi)</p>'],
]);
await renders('special characters are escaped in text', [
  ['Tom & Jerry <tom@example.com> said "hi"', '<p>Tom &amp; Jerry &lt;tom@example.com&gt; said &quot;hi&quot;</p>'],
  ['# a < b', '<h1>a &lt; b</h1>'],
  ['- <script>', '<ul><li>&lt;script&gt;</li></ul>'],
]);
await renders('special characters are escaped in links', [
  ['[a "b" <c>](https://x.test/?q="z"&r=1)',
    '<p><a href="https://x.test/?q=&quot;z&quot;&amp;r=1">a &quot;b&quot; &lt;c&gt;</a></p>'],
]);
await renders('unmatched markers are plain text', [
  ['5 * 3 = 15', '<p>5 * 3 = 15</p>'],
  ['**not closed', '<p>**not closed</p>'],
  ['a ` lonely tick', '<p>a ` lonely tick</p>'],
  ['[no url]', '<p>[no url]</p>'],
]);
await renders('empty input and windows line endings', [
  ['', ''],
  ['   \n\n  ', ''],
  ['# T\r\n\r\none\r\ntwo\r\n', '<h1>T</h1>\n<p>one two</p>'],
]);

const attribute = (tag, name) => new RegExp(`\\b${name}\\s*=\\s*["']?([^"'\\s>]+)`, 'i').exec(tag)?.[1];
await check('index.html has the editor, the preview and the module script', () => {
  const html = readFileSync('index.html', 'utf8');
  const tags = html.match(/<[a-zA-Z][^>]*>/g) ?? [];
  assert.ok(tags.some((tag) => /^<textarea\b/i.test(tag) && attribute(tag, 'id') === 'source'), 'textarea#source');
  assert.ok(tags.some((tag) => attribute(tag, 'id') === 'preview'), '#preview');
  assert.ok(tags.some((tag) => /^<script\b/i.test(tag) && attribute(tag, 'type') === 'module'
    && /^(\.\/)?src\/main\.js$/.test(attribute(tag, 'src') ?? '')), 'module script src/main.js');
});
await check('main.js imports render from markdown.js', () => {
  const source = readFileSync('src/main.js', 'utf8');
  assert.match(source, /import\s*\{[^}]*\brender\b[^}]*\}\s*from\s*['"]\.\/markdown\.js['"]/);
});

writeFileSync(path.join(process.env.HB_OUT, 'result.json'), JSON.stringify({ checks }, null, 2));
