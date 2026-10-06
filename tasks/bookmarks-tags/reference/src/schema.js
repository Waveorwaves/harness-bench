// What a bookmark is and what makes one valid.

export class ValidationError extends Error {
  constructor(field, message) {
    super(message);
    this.name = 'ValidationError';
    this.field = field;
  }
}

function cleanUrl(value) {
  let url;
  try {
    url = new URL(String(value).trim());
  } catch {
    throw new ValidationError('url', 'Not a valid URL');
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new ValidationError('url', 'Only http and https links can be saved');
  }
  return url.href;
}

function cleanTitle(value) {
  const title = typeof value === 'string' ? value.trim() : '';
  if (!title) throw new ValidationError('title', 'A title is required');
  if (title.length > 120) throw new ValidationError('title', 'A title can be at most 120 characters');
  return title;
}

function cleanDate(value) {
  const date = new Date(value);
  if (typeof value !== 'string' || Number.isNaN(date.getTime())) {
    throw new ValidationError('createdAt', 'Not a valid date');
  }
  return date.toISOString();
}

const TAG = /^[a-z0-9-]{1,20}$/;
const MAX_TAGS = 5;

function cleanTags(value) {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new ValidationError('tags', 'Tags must be a list');
  const tags = [];
  for (const raw of value) {
    if (typeof raw !== 'string') throw new ValidationError('tags', 'A tag must be text');
    const tag = raw.trim().toLowerCase();
    if (tag && !tags.includes(tag)) tags.push(tag);
  }
  if (tags.length > MAX_TAGS) throw new ValidationError('tags', `A bookmark can have at most ${MAX_TAGS} tags`);
  const bad = tags.find((tag) => !TAG.test(tag));
  if (bad !== undefined) {
    throw new ValidationError('tags', `"${bad}" is not a valid tag: use up to 20 letters, digits or hyphens`);
  }
  return tags;
}

export function normalizeBookmark(input) {
  return {
    url: cleanUrl(input.url),
    title: cleanTitle(input.title),
    createdAt: cleanDate(input.createdAt),
    tags: cleanTags(input.tags),
  };
}
