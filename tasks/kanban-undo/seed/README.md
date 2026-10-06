# Kanban

A small kanban board with undo and redo. No dependencies; open `index.html` through any static server.

## State

```js
{
  columns: [{ id: 'col-1', name: 'To do', cardIds: ['card-2', 'card-1'] }, ...],
  cards: { 'card-1': { id: 'card-1', title: 'Write tests' }, ... },
  nextCardId: 3,
}
```

## Actions (`src/store.js`)

Every action takes a state and returns a new state. Actions never modify the state they are given, so a state you already hold stays valid.

- `createBoard(columnNames)` makes an empty board.
- `addCard(state, columnId, title)` appends a card to a column. The title is trimmed and must not be empty.
- `moveCard(state, cardId, toColumnId, toIndex)` moves a card. `toIndex` is the position in the destination column counted after the card has been taken out of its old place; it is clamped to the valid range.
- `removeCard(state, cardId)` deletes a card.
- `renameCard(state, cardId, title)` changes a title.

Unknown column or card ids throw an `Error`.

## History (`src/history.js`)

`createHistory(initialState)` wraps a state with undo and redo.

- `history.apply(action, ...args)` runs `action(history.state, ...args)` and makes the result the current state.
- `history.undo()` restores the board exactly as it was before the most recent change. `history.redo()` re-applies it.
- A new change discards everything that could have been redone.
- Undo with nothing to undo, and redo with nothing to redo, leave the board unchanged.
- `history.canUndo` and `history.canRedo` say whether each is possible.

## View (`src/view.js`)

`renderBoard(state)` returns the board as an HTML string. Card titles are escaped.
