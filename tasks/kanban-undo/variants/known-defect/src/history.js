// Undo and redo around a board state. See README.md.

export function createHistory(initialState) {
  let present = initialState;
  const past = [];
  const future = [];

  return {
    get state() {
      return present;
    },
    get canUndo() {
      return past.length > 0;
    },
    get canRedo() {
      return future.length > 0;
    },
    apply(action, ...args) {
      const next = action(present, ...args);
      past.push(present);
      present = next;
      future.length = 0;
      return present;
    },
    undo() {
      if (past.length === 0) return present;
      future.push(present);
      present = past.pop();
      return present;
    },
    redo() {
      if (future.length === 0) return present;
      past.push(present);
      present = future.pop();
      return present;
    },
  };
}
