import { render } from './markdown.js';

const sourceTextarea = document.getElementById('source');
const previewDiv = document.getElementById('preview');

function updatePreview() {
  const markdown = sourceTextarea.value;
  const html = render(markdown);
  previewDiv.innerHTML = html;
}

// Update preview on input
sourceTextarea.addEventListener('input', updatePreview);

// Initial preview
updatePreview();
