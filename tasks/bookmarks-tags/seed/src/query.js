// Searching and ordering. Nothing here changes the list it is given.

export function search(bookmarks, text) {
  const needle = text.trim().toLowerCase();
  if (!needle) return [...bookmarks];
  return bookmarks.filter((bookmark) => bookmark.title.toLowerCase().includes(needle)
    || bookmark.url.toLowerCase().includes(needle));
}

export function sortBy(bookmarks, order) {
  const sorted = [...bookmarks];
  if (order === 'title') sorted.sort((a, b) => a.title.localeCompare(b.title));
  else if (order === 'newest') sorted.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  else throw new Error(`Unknown order: ${order}`);
  return sorted;
}
