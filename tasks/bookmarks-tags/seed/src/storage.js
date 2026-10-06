// The saved form of the store, with upgrades from older versions.

export const CURRENT_VERSION = 1;

// MIGRATIONS[n] upgrades saved data from version n to version n + 1.
export const MIGRATIONS = {};

export function emptyState() {
  return { bookmarks: [], nextId: 1 };
}

export function serialize(state) {
  return JSON.stringify({ version: CURRENT_VERSION, bookmarks: state.bookmarks, nextId: state.nextId });
}

export function deserialize(text) {
  if (text == null || text === '') return emptyState();
  let saved = JSON.parse(text);
  if (!Number.isInteger(saved.version) || saved.version < 1 || saved.version > CURRENT_VERSION) {
    throw new Error(`Cannot read saved data of version ${saved.version}`);
  }
  while (saved.version < CURRENT_VERSION) {
    saved = { ...MIGRATIONS[saved.version](saved), version: saved.version + 1 };
  }
  return { bookmarks: saved.bookmarks, nextId: saved.nextId };
}
