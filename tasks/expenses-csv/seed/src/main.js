import { CATEGORIES } from './model.js';
import { createStore } from './store.js';
import { renderTable } from './view.js';

const store = createStore();
const form = document.querySelector('#add');
const table = document.querySelector('#table');

form.elements.category.innerHTML = CATEGORIES.map((category) => `<option>${category}</option>`).join('');

function draw() {
  table.innerHTML = renderTable(store.all());
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const fields = new FormData(form);
  try {
    store.add({
      date: fields.get('date'),
      category: fields.get('category'),
      amountCents: Math.round(Number(fields.get('amount')) * 100),
      note: String(fields.get('note') ?? ''),
    });
    form.reset();
  } catch (error) {
    alert(error.message);
  }
  draw();
});

draw();
