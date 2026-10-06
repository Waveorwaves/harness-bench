Users of this kanban board report two problems. `README.md` describes how the board is meant to behave.

1. After moving a card to another column, Undo does not put it back. The same happens after adding or deleting a card.
2. Undo a change, then make a different change, then press Redo: the board jumps to a state that brings the undone change back. Redo should do nothing at that point.

Find and fix the causes so the code behaves as the README describes. Keep the exported functions of `src/store.js` and `src/history.js` and their signatures. The existing tests (`npm test`) must keep passing.
