// Hidden acceptance checks. Every expectation is stated in the prompt or the seed's README.
import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const checks = [];
const load = (file) => import(pathToFileURL(path.resolve(file)).href);

async function check(name, body) {
  try {
    await body(await load('src/store.js'), await load('src/history.js'));
    checks.push({ name, passed: true });
  } catch (error) {
    checks.push({ name, passed: false, detail: String(error?.message ?? error).slice(0, 400) });
  }
}

const copy = (value) => JSON.parse(JSON.stringify(value));
const layout = (state) => state.columns.map((column) => column.cardIds);

// Three columns; col-1 holds card-1..card-3, col-2 holds card-4.
function board(store) {
  let state = store.createBoard(['To do', 'Doing', 'Done']);
  for (const title of ['one', 'two', 'three']) state = store.addCard(state, 'col-1', title);
  return store.addCard(state, 'col-2', 'four');
}

await check('undo restores a card moved to another column', (store, { createHistory }) => {
  const history = createHistory(board(store));
  const before = copy(history.state);
  history.apply(store.moveCard, 'card-2', 'col-3', 0);
  assert.deepEqual(layout(history.state), [['card-1', 'card-3'], ['card-4'], ['card-2']]);
  assert.deepEqual(copy(history.undo()), before);
  assert.deepEqual(copy(history.state), before);
});

await check('undo restores the order after a move inside one column', (store, { createHistory }) => {
  const history = createHistory(board(store));
  history.apply(store.moveCard, 'card-1', 'col-1', 2);
  assert.deepEqual(layout(history.state)[0], ['card-2', 'card-3', 'card-1']);
  assert.deepEqual(layout(history.undo())[0], ['card-1', 'card-2', 'card-3']);
});

await check('undo removes an added card', (store, { createHistory }) => {
  const history = createHistory(board(store));
  const before = copy(history.state);
  history.apply(store.addCard, 'col-3', 'five');
  assert.deepEqual(layout(history.state)[2], ['card-5']);
  assert.deepEqual(copy(history.undo()), before);
});

await check('undo brings back a deleted card in its place', (store, { createHistory }) => {
  const history = createHistory(board(store));
  const before = copy(history.state);
  history.apply(store.removeCard, 'card-2');
  assert.deepEqual(layout(history.state)[0], ['card-1', 'card-3']);
  assert.deepEqual(copy(history.undo()), before);
});

await check('redo re-applies an undone move', (store, { createHistory }) => {
  const history = createHistory(board(store));
  history.apply(store.moveCard, 'card-3', 'col-2', 0);
  const after = copy(history.state);
  history.undo();
  assert.equal(history.canRedo, true);
  assert.deepEqual(copy(history.redo()), after);
  assert.deepEqual(layout(history.state), [['card-1', 'card-2'], ['card-3', 'card-4'], []]);
});

await check('several undos and redos walk the history in order', (store, { createHistory }) => {
  const history = createHistory(board(store));
  const snapshots = [copy(history.state)];
  history.apply(store.moveCard, 'card-1', 'col-3', 0);
  snapshots.push(copy(history.state));
  history.apply(store.addCard, 'col-3', 'five');
  snapshots.push(copy(history.state));
  history.apply(store.removeCard, 'card-4');
  snapshots.push(copy(history.state));
  history.apply(store.renameCard, 'card-2', 'TWO');
  snapshots.push(copy(history.state));
  for (let step = 3; step >= 0; step -= 1) assert.deepEqual(copy(history.undo()), snapshots[step], `undo to ${step}`);
  assert.equal(history.canUndo, false);
  for (let step = 1; step <= 4; step += 1) assert.deepEqual(copy(history.redo()), snapshots[step], `redo to ${step}`);
  assert.equal(history.canRedo, false);
});

await check('a new change discards what could be redone', (store, { createHistory }) => {
  const history = createHistory(board(store));
  history.apply(store.renameCard, 'card-1', 'ONE');
  history.undo();
  history.apply(store.renameCard, 'card-2', 'TWO');
  const current = copy(history.state);
  assert.equal(history.canRedo, false);
  assert.deepEqual(copy(history.redo()), current);
  assert.equal(history.state.cards['card-1'].title, 'one');
});

await check('redo stays discarded after a move following an undo', (store, { createHistory }) => {
  const history = createHistory(board(store));
  history.apply(store.addCard, 'col-3', 'five');
  history.apply(store.addCard, 'col-3', 'six');
  history.undo();
  history.undo();
  history.apply(store.moveCard, 'card-4', 'col-3', 0);
  history.redo();
  assert.deepEqual(layout(history.state), [['card-1', 'card-2', 'card-3'], [], ['card-4']]);
  assert.deepEqual(Object.keys(history.state.cards).sort(), ['card-1', 'card-2', 'card-3', 'card-4']);
  assert.deepEqual(layout(history.undo()), [['card-1', 'card-2', 'card-3'], ['card-4'], []]);
});

await check('undo and redo with nothing to do leave the board unchanged', (store, { createHistory }) => {
  const history = createHistory(board(store));
  const start = copy(history.state);
  assert.equal(history.canUndo, false);
  assert.deepEqual(copy(history.undo()), start);
  assert.deepEqual(copy(history.redo()), start);
  history.apply(store.moveCard, 'card-1', 'col-2', 0);
  const moved = copy(history.state);
  assert.deepEqual(copy(history.redo()), moved);
});

await check('addCard does not modify the state it is given', (store) => {
  const state = board(store);
  const before = copy(state);
  const next = store.addCard(state, 'col-1', 'five');
  assert.deepEqual(copy(state), before);
  assert.deepEqual(layout(next)[0], ['card-1', 'card-2', 'card-3', 'card-5']);
});

await check('moveCard does not modify the state it is given', (store) => {
  const state = board(store);
  const before = copy(state);
  const next = store.moveCard(state, 'card-1', 'col-2', 1);
  assert.deepEqual(copy(state), before);
  assert.deepEqual(layout(next), [['card-2', 'card-3'], ['card-4', 'card-1'], []]);
});

await check('removeCard does not modify the state it is given', (store) => {
  const state = board(store);
  const before = copy(state);
  const next = store.removeCard(state, 'card-3');
  assert.deepEqual(copy(state), before);
  assert.deepEqual(layout(next)[0], ['card-1', 'card-2']);
  assert.equal(next.cards['card-3'], undefined);
});

await check('existing action behaviour is preserved', (store) => {
  const state = board(store);
  assert.deepEqual(layout(store.moveCard(state, 'card-4', 'col-1', -5))[0], ['card-4', 'card-1', 'card-2', 'card-3']);
  assert.deepEqual(layout(store.moveCard(board(store), 'card-2', 'col-1', 99))[0], ['card-1', 'card-3', 'card-2']);
  assert.deepEqual(layout(store.moveCard(board(store), 'card-3', 'col-1', 1))[0], ['card-1', 'card-3', 'card-2']);
  assert.equal(store.addCard(board(store), 'col-3', '  padded  ').cards['card-5'].title, 'padded');
  assert.equal(store.addCard(board(store), 'col-3', 'x').nextCardId, 6);
  assert.throws(() => store.addCard(board(store), 'col-1', '  '));
  assert.throws(() => store.addCard(board(store), 'col-7', 'x'));
  assert.throws(() => store.moveCard(board(store), 'card-9', 'col-1', 0));
  assert.throws(() => store.moveCard(board(store), 'card-1', 'col-9', 0));
  assert.throws(() => store.removeCard(board(store), 'card-9'));
});

await check('the view still renders cards in order and escaped', async (store) => {
  const { renderBoard } = await load('src/view.js');
  let state = store.createBoard(['A & B']);
  state = store.addCard(state, 'col-1', '<i>first</i>');
  state = store.addCard(state, 'col-1', 'second');
  state = store.moveCard(state, 'card-2', 'col-1', 0);
  const html = renderBoard(state);
  assert.ok(html.includes('A &amp; B'));
  assert.ok(html.includes('&lt;i&gt;first&lt;/i&gt;'));
  assert.ok(html.indexOf('data-id="card-2"') < html.indexOf('data-id="card-1"'));
});

writeFileSync(path.join(process.env.HB_OUT, 'result.json'), JSON.stringify({ checks }, null, 2));
