// Hidden acceptance checks. Every expectation is stated in the prompt or the seed's README.
import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
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

const when = '2026-03-01T09:30:00.000Z';
const fields = (extra = {}) => ({ url: 'https://example.com/', title: 'Example', createdAt: when, ...extra });
const tagError = (error) => error?.name === 'ValidationError' && error.field === 'tags';
const plain = (value) => JSON.parse(JSON.stringify(value));

function memory(initial = null) {
  let text = initial;
  return { read: () => text, write: (next) => { text = next; }, get text() { return text; } };
}

const bookmark = (id, title, tags, url = `https://site${id}.example/`, createdAt = when) => ({ id, url, title, createdAt, tags });

// --- schema ---

await check('schema: tags default to an empty list and clean tags pass through', async () => {
  const { normalizeBookmark } = await load('src/schema.js');
  assert.deepEqual(normalizeBookmark(fields()), fields({ tags: [] }));
  assert.deepEqual(normalizeBookmark(fields({ tags: [] })).tags, []);
  assert.deepEqual(normalizeBookmark(fields({ tags: ['news', 'web-dev', 'es2026'] })).tags, ['news', 'web-dev', 'es2026']);
});

await check('schema: tags are trimmed, lowercased, emptied and deduplicated', async () => {
  const { normalizeBookmark } = await load('src/schema.js');
  assert.deepEqual(normalizeBookmark(fields({ tags: ['  News ', 'WEB', '', '   ', 'news', 'Web', 'tools'] })).tags,
    ['news', 'web', 'tools']);
});

await check('schema: tags must be a list', async () => {
  const { normalizeBookmark } = await load('src/schema.js');
  for (const tags of ['news', 7, { 0: 'news' }, true]) {
    assert.throws(() => normalizeBookmark(fields({ tags })), tagError, JSON.stringify(tags));
  }
});

await check('schema: tag characters and length', async () => {
  const { normalizeBookmark } = await load('src/schema.js');
  for (const tag of ['c++', 'web dev', 'café', 'under_score', 'a'.repeat(21), 'a/b']) {
    assert.throws(() => normalizeBookmark(fields({ tags: ['ok', tag] })), tagError, tag);
  }
  assert.deepEqual(normalizeBookmark(fields({ tags: ['a'.repeat(20), '2026', 'a-b-c', 'X'] })).tags,
    ['a'.repeat(20), '2026', 'a-b-c', 'x']);
});

await check('schema: at most five tags, counted after cleaning', async () => {
  const { normalizeBookmark } = await load('src/schema.js');
  assert.throws(() => normalizeBookmark(fields({ tags: ['a', 'b', 'c', 'd', 'e', 'f'] })), tagError);
  assert.deepEqual(normalizeBookmark(fields({ tags: ['a', 'b', ' A', '', 'c', 'd', 'B ', 'e'] })).tags,
    ['a', 'b', 'c', 'd', 'e']);
});

await check('schema: earlier validation still works', async () => {
  const { normalizeBookmark } = await load('src/schema.js');
  const clean = normalizeBookmark({ url: ' https://example.com/path ', title: '  Spaced  ', createdAt: when, tags: ['t'] });
  assert.deepEqual(clean, { url: 'https://example.com/path', title: 'Spaced', createdAt: when, tags: ['t'] });
  assert.throws(() => normalizeBookmark(fields({ url: 'javascript:alert(1)' })), (error) => error.field === 'url');
  assert.throws(() => normalizeBookmark(fields({ title: 'x'.repeat(121) })), (error) => error.field === 'title');
  assert.throws(() => normalizeBookmark(fields({ createdAt: 'yesterday' })), (error) => error.field === 'createdAt');
});

// --- store ---

await check('store: add keeps cleaned tags', async () => {
  const { createStore } = await load('src/store.js');
  const store = createStore(memory());
  assert.deepEqual(store.add(fields({ tags: [' News', 'news', 'Web'] })).tags, ['news', 'web']);
  assert.deepEqual(store.add(fields({ title: 'Plain' })).tags, []);
  assert.deepEqual(store.list().map((item) => item.tags), [['news', 'web'], []]);
  assert.throws(() => store.add(fields({ tags: ['not ok'] })), tagError);
  assert.equal(store.list().length, 2);
});

await check('store: update replaces tags only when they are given', async () => {
  const { createStore } = await load('src/store.js');
  const store = createStore(memory());
  const { id } = store.add(fields({ tags: ['news', 'web'] }));
  assert.deepEqual(store.update(id, { title: 'Renamed' }).tags, ['news', 'web']);
  assert.deepEqual(store.update(id, { tags: ['Tools'] }).tags, ['tools']);
  assert.equal(store.list()[0].title, 'Renamed');
  assert.deepEqual(store.update(id, { tags: [] }).tags, []);
  assert.throws(() => store.update(id, { tags: 'tools' }), tagError);
});

await check('store: tags survive a reload', async () => {
  const { createStore } = await load('src/store.js');
  const adapter = memory();
  const store = createStore(adapter);
  store.add(fields({ tags: ['news'] }));
  const second = store.add(fields({ title: 'Second' }));
  store.update(second.id, { tags: ['web', 'tools'] });
  assert.deepEqual(plain(createStore(adapter).list()), [
    { id: 1, ...fields({ tags: ['news'] }) },
    { id: 2, ...fields({ title: 'Second', tags: ['web', 'tools'] }) },
  ]);
});

// --- storage ---

const version1 = JSON.stringify({
  version: 1,
  bookmarks: [
    { id: 1, url: 'https://a.example/', title: 'A', createdAt: when },
    { id: 4, url: 'https://b.example/', title: 'B', createdAt: when },
  ],
  nextId: 5,
});

await check('storage: version 1 data loads with empty tags', async () => {
  const { deserialize } = await load('src/storage.js');
  assert.deepEqual(plain(deserialize(version1)), {
    bookmarks: [
      { id: 1, url: 'https://a.example/', title: 'A', createdAt: when, tags: [] },
      { id: 4, url: 'https://b.example/', title: 'B', createdAt: when, tags: [] },
    ],
    nextId: 5,
  });
});

await check('storage: a store opened on version 1 data writes version 2', async () => {
  const { createStore } = await load('src/store.js');
  const adapter = memory(version1);
  const store = createStore(adapter);
  assert.deepEqual(store.list().map((item) => item.tags), [[], []]);
  assert.equal(store.add(fields({ tags: ['new'] })).id, 5);
  const saved = JSON.parse(adapter.text);
  assert.equal(saved.version, 2);
  assert.deepEqual(saved.bookmarks.map((item) => item.tags), [[], [], ['new']]);
  assert.deepEqual(createStore(adapter).list().map((item) => item.id), [1, 4, 5]);
});

await check('storage: saves version 2 and still rejects unknown versions', async () => {
  const { deserialize, serialize } = await load('src/storage.js');
  const state = { bookmarks: [bookmark(1, 'A', ['x', 'y'])], nextId: 2 };
  assert.equal(JSON.parse(serialize(state)).version, 2);
  assert.deepEqual(plain(deserialize(serialize(state))), state);
  assert.deepEqual(plain(deserialize(null)), { bookmarks: [], nextId: 1 });
  for (const version of [0, 3, 99]) {
    assert.throws(() => deserialize(JSON.stringify({ version, bookmarks: [], nextId: 1 })), `version ${version}`);
  }
});

// --- query ---

const library = [
  bookmark(1, 'Daily news', ['news', 'reading']),
  bookmark(2, 'MDN', ['javascript', 'docs', 'reading']),
  bookmark(3, 'Node documentation', ['docs', 'node']),
  bookmark(4, 'Untagged', []),
  bookmark(5, 'Script kiddies', ['news'], 'https://java.example/'),
];

await check('query: search also looks in tags', async () => {
  const { search } = await load('src/query.js');
  const ids = (text) => search(library, text).map((item) => item.id);
  assert.deepEqual(ids('reading'), [1, 2]);
  assert.deepEqual(ids('JAVA'), [2, 5]);
  assert.deepEqual(ids('doc'), [2, 3]);
  assert.deepEqual(ids('script'), [2, 5]);
  assert.deepEqual(ids('untagged'), [4]);
  assert.deepEqual(ids('  '), [1, 2, 3, 4, 5]);
  assert.deepEqual(ids('nothing-matches'), []);
});

await check('query: filterByTag matches whole tags', async () => {
  const { filterByTag } = await load('src/query.js');
  const ids = (tag) => filterByTag(library, tag).map((item) => item.id);
  assert.deepEqual(ids('docs'), [2, 3]);
  assert.deepEqual(ids('  News '), [1, 5]);
  assert.deepEqual(ids('doc'), []);
  assert.deepEqual(ids('java'), []);
  assert.deepEqual(ids('missing'), []);
});

await check('query: allTags counts and orders', async () => {
  const { allTags } = await load('src/query.js');
  assert.deepEqual(plain(allTags(library)), [
    { tag: 'docs', count: 2 }, { tag: 'news', count: 2 }, { tag: 'reading', count: 2 },
    { tag: 'javascript', count: 1 }, { tag: 'node', count: 1 },
  ]);
  assert.deepEqual(allTags([]), []);
  assert.deepEqual(allTags([bookmark(1, 'None', [])]), []);
});

await check('query: sorting is unchanged', async () => {
  const { sortBy } = await load('src/query.js');
  const list = [bookmark(1, 'b', [], undefined, '2026-01-01T00:00:00.000Z'), bookmark(2, 'a', ['t'], undefined, '2026-02-01T00:00:00.000Z')];
  assert.deepEqual(sortBy(list, 'title').map((item) => item.id), [2, 1]);
  assert.deepEqual(sortBy(list, 'newest').map((item) => item.id), [2, 1]);
  assert.deepEqual(list.map((item) => item.id), [1, 2]);
  assert.throws(() => sortBy(list, 'random'));
});

// --- exchange ---

await check('exchange: export writes version 2 with tags', async () => {
  const { exportJson } = await load('src/exchange.js');
  assert.deepEqual(JSON.parse(exportJson([bookmark(1, 'A', ['x', 'y']), bookmark(2, 'B', [])])), {
    format: 'bookmarks',
    version: 2,
    items: [
      { url: 'https://site1.example/', title: 'A', createdAt: when, tags: ['x', 'y'] },
      { url: 'https://site2.example/', title: 'B', createdAt: when, tags: [] },
    ],
  });
});

await check('exchange: import reads version 1 and version 2 files', async () => {
  const { exportJson, importJson } = await load('src/exchange.js');
  const item = { url: 'https://a.example/', title: 'A', createdAt: when };
  assert.deepEqual(plain(importJson(JSON.stringify({ format: 'bookmarks', version: 1, items: [item] }))), [{ ...item, tags: [] }]);
  assert.deepEqual(plain(importJson(JSON.stringify({ format: 'bookmarks', version: 2, items: [{ ...item, tags: [' News', 'web'] }, item] }))),
    [{ ...item, tags: ['news', 'web'] }, { ...item, tags: [] }]);
  const list = [bookmark(1, 'A', ['x', 'y']), bookmark(2, 'B', [])];
  assert.deepEqual(plain(importJson(exportJson(list))), list.map(({ id, ...rest }) => rest));
});

await check('exchange: import still rejects other files', async () => {
  const { importJson } = await load('src/exchange.js');
  assert.throws(() => importJson(JSON.stringify({ format: 'bookmarks', version: 3, items: [] })));
  assert.throws(() => importJson(JSON.stringify({ format: 'bookmarks', version: 0, items: [] })));
  assert.throws(() => importJson(JSON.stringify({ format: 'notes', version: 2, items: [] })));
  assert.throws(() => importJson(JSON.stringify({ format: 'bookmarks', version: 2, items: [{ url: 'https://a.example/', title: 'A', createdAt: when, tags: ['bad tag'] }] })), tagError);
});

// --- view ---

await check('view: tags follow the link, and untagged bookmarks render as before', async () => {
  const { renderList } = await load('src/view.js');
  assert.equal(renderList([bookmark(7, 'Tagged <b>', ['news', 'web-dev'], 'https://a.example/?q="x"'), bookmark(8, 'Plain', [])]),
    '<ul class="bookmarks">'
    + '<li data-id="7"><a href="https://a.example/?q=&quot;x&quot;">Tagged &lt;b&gt;</a><span class="tag">news</span><span class="tag">web-dev</span></li>'
    + '<li data-id="8"><a href="https://site8.example/">Plain</a></li>'
    + '</ul>');
  assert.equal(renderList([]), '<ul class="bookmarks"></ul>');
});

writeFileSync(path.join(process.env.HB_OUT, 'result.json'), JSON.stringify({ checks }, null, 2));
