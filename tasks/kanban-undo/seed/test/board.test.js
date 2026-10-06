import assert from 'node:assert/strict';
import test from 'node:test';

import { createHistory } from '../src/history.js';
import { addCard, createBoard, moveCard, removeCard, renameCard } from '../src/store.js';
import { renderBoard } from '../src/view.js';

function sample() {
  let state = createBoard(['To do', 'Done']);
  state = addCard(state, 'col-1', 'Write tests');
  state = addCard(state, 'col-1', ' Ship it ');
  return state;
}

test('addCard appends a trimmed card', () => {
  const state = sample();
  assert.deepEqual(state.columns[0].cardIds, ['card-1', 'card-2']);
  assert.equal(state.cards['card-2'].title, 'Ship it');
  assert.throws(() => addCard(state, 'col-1', '   '));
  assert.throws(() => addCard(state, 'col-9', 'x'));
});

test('moveCard moves between columns and clamps the index', () => {
  const state = moveCard(sample(), 'card-1', 'col-2', 99);
  assert.deepEqual(state.columns.map((column) => column.cardIds), [['card-2'], ['card-1']]);
});

test('removeCard and renameCard', () => {
  const state = renameCard(removeCard(sample(), 'card-1'), 'card-2', 'Shipped');
  assert.deepEqual(state.columns[0].cardIds, ['card-2']);
  assert.deepEqual(Object.keys(state.cards), ['card-2']);
  assert.equal(state.cards['card-2'].title, 'Shipped');
});

test('history undoes and redoes a rename', () => {
  const history = createHistory(sample());
  history.apply(renameCard, 'card-1', 'Write more tests');
  assert.equal(history.undo().cards['card-1'].title, 'Write tests');
  assert.equal(history.redo().cards['card-1'].title, 'Write more tests');
  assert.equal(history.canRedo, false);
});

test('renderBoard escapes titles', () => {
  const html = renderBoard(addCard(createBoard(['A']), 'col-1', '<b>bold</b>'));
  assert.ok(html.includes('&lt;b&gt;bold&lt;/b&gt;'));
});
