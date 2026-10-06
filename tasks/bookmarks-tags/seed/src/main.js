import { search, sortBy } from './query.js';
import { createStore, localStorageAdapter } from './store.js';
import { renderList } from './view.js';

const store = createStore(localStorageAdapter());
const form = document.querySelector('#add');
const box = document.querySelector('#search');
const list = document.querySelector('#list');

function draw() {
  list.innerHTML = renderList(sortBy(search(store.list(), box.value), 'newest'));
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const fields = new FormData(form);
  try {
    store.add({ url: fields.get('url'), title: fields.get('title') });
    form.reset();
  } catch (error) {
    alert(error.message);
  }
  draw();
});

box.addEventListener('input', draw);
draw();
