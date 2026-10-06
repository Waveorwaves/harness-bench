import { render } from './markdown.js';

const source = document.querySelector('#source');
const preview = document.querySelector('#preview');

function update() {
  preview.innerHTML = render(source.value);
}

source.addEventListener('input', update);
update();
