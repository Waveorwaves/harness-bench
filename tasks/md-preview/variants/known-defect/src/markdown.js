// HTML escape function
function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Apply inline formatting (code, bold, italic, links)
// Process markdown patterns carefully to handle nested cases
function applyInlineFormatting(text) {
  let result = '';
  let i = 0;

  while (i < text.length) {
    // Check for backtick code: `text`
    if (text[i] === '`') {
      const endIdx = text.indexOf('`', i + 1);
      if (endIdx !== -1) {
        const code = text.slice(i + 1, endIdx);
        result += '<code>' + escapeHtml(code) + '</code>';
        i = endIdx + 1;
        continue;
      }
    }

    // Check for link: [text](url)
    if (text[i] === '[') {
      const closeIdx = text.indexOf(']', i + 1);
      if (closeIdx !== -1 && closeIdx + 1 < text.length && text[closeIdx + 1] === '(') {
        const closeParenIdx = text.indexOf(')', closeIdx + 2);
        if (closeParenIdx !== -1) {
          const linkText = text.slice(i + 1, closeIdx);
          const url = text.slice(closeIdx + 2, closeParenIdx);

          if (/^(https?:\/\/|mailto:|\/|#)/.test(url)) {
            result += '<a href="' + escapeHtml(url) + '">' + escapeHtml(linkText) + '</a>';
            i = closeParenIdx + 1;
            continue;
          }
        }
      }
    }

    // Check for bold: **text**
    if (text[i] === '*' && i + 1 < text.length && text[i + 1] === '*') {
      const endIdx = text.indexOf('**', i + 2);
      if (endIdx !== -1) {
        const bold = text.slice(i + 2, endIdx);
        result += '<strong>' + escapeHtml(bold) + '</strong>';
        i = endIdx + 2;
        continue;
      }
    }

    // Check for italic: *text*
    if (text[i] === '*') {
      const endIdx = text.indexOf('*', i + 1);
      if (endIdx !== -1) {
        const italic = text.slice(i + 1, endIdx);
        result += '<em>' + escapeHtml(italic) + '</em>';
        i = endIdx + 1;
        continue;
      }
    }

    // Regular character - just escape it
    result += escapeHtml(text[i]);
    i++;
  }

  return result;
}

export function render(markdown) {
  if (!markdown || markdown.trim() === '') {
    return '';
  }

  // Normalize line endings
  markdown = markdown.replace(/\r\n/g, '\n');

  // Split into blocks by blank lines (one or more)
  const blocks = markdown.split(/\n\s*\n/);
  const results = [];

  for (const block of blocks) {
    if (!block.trim()) continue;

    const lines = block.split('\n');
    const trimmedLines = lines.map(l => l.trim());
    const firstLine = trimmedLines[0];

    // Check for heading (one-line block)
    const headingMatch = firstLine.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch && lines.length === 1) {
      const level = headingMatch[1].length;
      const content = headingMatch[2];
      const html = applyInlineFormatting(content);
      results.push(`<h${level}>${html}</h${level}>`);
      continue;
    }

    // Check for code block (starts with ``` at line beginning - on raw line, not trimmed)
    if (lines[0].trim().startsWith('```')) {
      // Find the ending ``` (exactly three backticks, trimmed)
      let endIdx = -1;
      for (let i = 1; i < lines.length; i++) {
        if (lines[i].trim() === '```') {
          endIdx = i;
          break;
        }
      }

      if (endIdx !== -1) {
        // Extract code lines with original formatting (not trimmed)
        const codeLines = [];
        for (let i = 1; i < endIdx; i++) {
          codeLines.push(lines[i]);
        }
        const codeContent = codeLines.join('\n');
        // Escape HTML in code
        const escaped = escapeHtml(codeContent);
        results.push(`<pre><code>${escaped}</code></pre>`);
        continue;
      }
    }

    // Check for list (all lines start with - )
    const isListBlock = trimmedLines.every(line => line.startsWith('- '));
    if (isListBlock) {
      const listItems = trimmedLines.map(line => {
        const itemText = line.slice(2); // Remove "- "
        const html = applyInlineFormatting(itemText);
        return `<li>${html}</li>`;
      });
      results.push(`<ul>${listItems.join('')}</ul>`);
      continue;
    }

    // Paragraph - join lines with space (trim leading/trailing on each line)
    const paragraphText = trimmedLines.join(' ');
    const html = applyInlineFormatting(paragraphText);
    results.push(`<p>${html}</p>`);
  }

  return results.join('\n');
}
