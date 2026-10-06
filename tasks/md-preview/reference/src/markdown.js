const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const SAFE_URL = /^(https?:\/\/|mailto:|\/|#)/;
const INLINE = /`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
const FENCE = '```';

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (character) => ESCAPES[character]);
}

function inline(text) {
  let html = '';
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const [whole, code, label, url, strong, emphasis] = match;
    html += escapeHtml(text.slice(last, match.index));
    if (code !== undefined) html += `<code>${escapeHtml(code)}</code>`;
    else if (label !== undefined) {
      html += SAFE_URL.test(url) ? `<a href="${escapeHtml(url)}">${escapeHtml(label)}</a>` : escapeHtml(whole);
    } else if (strong !== undefined) html += `<strong>${escapeHtml(strong)}</strong>`;
    else html += `<em>${escapeHtml(emphasis)}</em>`;
    last = match.index + whole.length;
  }
  return html + escapeHtml(text.slice(last));
}

function block(lines) {
  const heading = lines.length === 1 && /^(#{1,3}) (.*)$/.exec(lines[0]);
  if (heading) return `<h${heading[1].length}>${inline(heading[2].trim())}</h${heading[1].length}>`;
  if (lines.every((line) => line.startsWith('- '))) {
    return `<ul>${lines.map((line) => `<li>${inline(line.slice(2).trim())}</li>`).join('')}</ul>`;
  }
  return `<p>${inline(lines.join(' '))}</p>`;
}

export function render(markdown) {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (line === '') {
      index += 1;
    } else if (line.startsWith(FENCE)) {
      const code = [];
      index += 1;
      while (index < lines.length && lines[index].trim() !== FENCE) code.push(lines[index++]);
      index += 1;
      blocks.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
    } else {
      const current = [];
      while (index < lines.length && lines[index].trim() !== '') current.push(lines[index++].trim());
      blocks.push(block(current));
    }
  }
  return blocks.join('\n');
}
