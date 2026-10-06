// Holds the bookmarks and saves after every change.

import { normalizeBookmark } from './schema.js';
import { deserialize, serialize } from './storage.js';

export function createStore(adapter) {
  const state = deserialize(adapter.read());
  const save = () => adapter.write(serialize(state));

  function find(id) {
    const bookmark = state.bookmarks.find((candidate) => candidate.id === id);
    if (!bookmark) throw new Error(`No bookmark with id ${id}`);
    return bookmark;
  }

  return {
    list() {
      return state.bookmarks.map((bookmark) => ({ ...bookmark }));
    },
    add(input) {
      const fields = normalizeBookmark({ createdAt: new Date().toISOString(), ...input });
      const bookmark = { id: state.nextId, ...fields };
      state.nextId += 1;
      state.bookmarks.push(bookmark);
      save();
      return { ...bookmark };
    },
    update(id, changes) {
      const bookmark = find(id);
      const fields = normalizeBookmark({
        url: changes.url ?? bookmark.url,
        title: changes.title ?? bookmark.title,
        createdAt: bookmark.createdAt,
      });
      Object.assign(bookmark, fields);
      save();
      return { ...bookmark };
    },
    remove(id) {
      state.bookmarks.splice(state.bookmarks.indexOf(find(id)), 1);
      save();
    },
  };
}

// Adapter for the browser.
export function localStorageAdapter(key = 'bookmarks') {
  return {
    read: () => globalThis.localStorage.getItem(key),
    write: (text) => globalThis.localStorage.setItem(key, text),
  };
}
