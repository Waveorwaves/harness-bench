// The file format for moving bookmarks between browsers.

import { normalizeBookmark } from './schema.js';

const FORMAT = 'bookmarks';
export const EXPORT_VERSION = 2;
const READABLE_VERSIONS = [1, 2];

export function exportJson(bookmarks) {
  return JSON.stringify({
    format: FORMAT,
    version: EXPORT_VERSION,
    items: bookmarks.map(({ url, title, createdAt, tags }) => ({ url, title, createdAt, tags })),
  }, null, 2);
}

// Returns clean bookmark fields (no ids); the caller adds them to a store.
export function importJson(text) {
  const file = JSON.parse(text);
  if (file.format !== FORMAT) throw new Error('Not a bookmarks file');
  if (!READABLE_VERSIONS.includes(file.version)) throw new Error(`Cannot read bookmarks file of version ${file.version}`);
  return file.items.map((item) => normalizeBookmark(item));
}
