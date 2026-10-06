import assert from 'node:assert/strict';
import test from 'node:test';

import { exportJson, importJson } from '../src/exchange.js';
import { search, sortBy } from '../src/query.js';
import { normalizeBookmark, ValidationError } from '../src/schema.js';
import { deserialize, serialize } from '../src/storage.js';
import { createStore } from '../src/store.js';
import { renderList } from '../src/view.js';

function memory(initial = null) {
  let text = initial;
  return { read: () => text, write: (next) => { text = next; }, get text() { return text; } };
}

const when = '2026-03-01T09:30:00.000Z';

test('normalizeBookmark cleans and validates', () => {
  assert.deepEqual(normalizeBookmark({ url: ' https://example.com ', title: ' Example ', createdAt: when }),
    { url: 'https://example.com/', title: 'Example', createdAt: when });
  assert.throws(() => normalizeBookmark({ url: 'ftp://example.com', title: 'x', createdAt: when }),
    (error) => error instanceof ValidationError && error.field === 'url');
  assert.throws(() => normalizeBookmark({ url: 'https://example.com', title: ' ', createdAt: when }),
    (error) => error.field === 'title');
});

test('the store saves every change and reloads it', () => {
  const adapter = memory();
  const store = createStore(adapter);
  const first = store.add({ url: 'https://a.example', title: 'A', createdAt: when });
  store.add({ url: 'https://b.example', title: 'B', createdAt: when });
  store.update(first.id, { title: 'Alpha' });
  store.remove(2);
  assert.deepEqual(createStore(adapter).list(), [{ id: 1, url: 'https://a.example/', title: 'Alpha', createdAt: when }]);
  assert.equal(createStore(adapter).add({ url: 'https://c.example', title: 'C' }).id, 3);
});

test('storage round trip', () => {
  const state = { bookmarks: [{ id: 1, url: 'https://a.example/', title: 'A', createdAt: when }], nextId: 2 };
  assert.deepEqual(deserialize(serialize(state)), state);
  assert.deepEqual(deserialize(null), { bookmarks: [], nextId: 1 });
  assert.throws(() => deserialize(JSON.stringify({ version: 99, bookmarks: [], nextId: 1 })));
});

test('search, sort, exchange and view', () => {
  const list = [
    { id: 1, url: 'https://b.example/', title: 'Bravo', createdAt: '2026-01-01T00:00:00.000Z' },
    { id: 2, url: 'https://a.example/docs', title: 'alpha <1>', createdAt: '2026-02-01T00:00:00.000Z' },
  ];
  assert.deepEqual(search(list, 'DOCS').map((bookmark) => bookmark.id), [2]);
  assert.deepEqual(sortBy(list, 'title').map((bookmark) => bookmark.id), [2, 1]);
  assert.deepEqual(sortBy(list, 'newest').map((bookmark) => bookmark.id), [2, 1]);
  assert.deepEqual(importJson(exportJson(list)), list.map(({ id, ...fields }) => fields));
  assert.equal(renderList(list.slice(1)),
    '<ul class="bookmarks"><li data-id="2"><a href="https://a.example/docs">alpha &lt;1&gt;</a></li></ul>');
});
