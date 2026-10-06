// Renders the list as HTML.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (character) => ESCAPES[character]);

function renderItem(bookmark) {
  const tags = bookmark.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join('');
  return `<li data-id="${bookmark.id}"><a href="${escapeHtml(bookmark.url)}">${escapeHtml(bookmark.title)}</a>${tags}</li>`;
}

export function renderList(bookmarks) {
  return `<ul class="bookmarks">${bookmarks.map(renderItem).join('')}</ul>`;
}
