// Searching and ordering. Nothing here changes the list it is given.

export function search(bookmarks, text) {
  const needle = text.trim().toLowerCase();
  if (!needle) return [...bookmarks];
  return bookmarks.filter((bookmark) => bookmark.title.toLowerCase().includes(needle)
    || bookmark.url.toLowerCase().includes(needle)
    || bookmark.tags.some((tag) => tag.includes(needle)));
}

export function filterByTag(bookmarks, tag) {
  const wanted = tag.trim().toLowerCase();
  return bookmarks.filter((bookmark) => bookmark.tags.includes(wanted));
}

export function allTags(bookmarks) {
  const counts = new Map();
  for (const bookmark of bookmarks) {
    for (const tag of bookmark.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  }
  return [...counts]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || (a.tag < b.tag ? -1 : 1));
}

export function sortBy(bookmarks, order) {
  const sorted = [...bookmarks];
  if (order === 'title') sorted.sort((a, b) => a.title.localeCompare(b.title));
  else if (order === 'newest') sorted.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  else throw new Error(`Unknown order: ${order}`);
  return sorted;
}
