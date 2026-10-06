import { createHistory } from './history.js';
import { addCard, createBoard, moveCard, removeCard } from './store.js';
import { renderBoard } from './view.js';

const history = createHistory(createBoard(['To do', 'Doing', 'Done']));
const board = document.querySelector('#board');
const undo = document.querySelector('#undo');
const redo = document.querySelector('#redo');

function draw() {
  board.innerHTML = renderBoard(history.state);
  undo.disabled = !history.canUndo;
  redo.disabled = !history.canRedo;
}

board.addEventListener('submit', (event) => {
  event.preventDefault();
  const column = event.target.closest('.column');
  const title = new FormData(event.target).get('title');
  if (String(title).trim()) history.apply(addCard, column.dataset.id, String(title));
  draw();
});

board.addEventListener('dragstart', (event) => {
  event.dataTransfer.setData('text/plain', event.target.dataset.id);
});
board.addEventListener('dragover', (event) => event.preventDefault());
board.addEventListener('drop', (event) => {
  event.preventDefault();
  const column = event.target.closest('.column');
  if (!column) return;
  const cardId = event.dataTransfer.getData('text/plain');
  const before = event.target.closest('.card');
  const cards = [...column.querySelectorAll('.card')].filter((card) => card.dataset.id !== cardId);
  history.apply(moveCard, cardId, column.dataset.id, before ? cards.indexOf(before) : cards.length);
  draw();
});

board.addEventListener('dblclick', (event) => {
  const card = event.target.closest('.card');
  if (card) history.apply(removeCard, card.dataset.id);
  draw();
});

undo.addEventListener('click', () => { history.undo(); draw(); });
redo.addEventListener('click', () => { history.redo(); draw(); });
draw();
