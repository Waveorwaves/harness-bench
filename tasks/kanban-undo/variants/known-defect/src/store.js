// Board state and the actions that change it. See README.md.

export function createBoard(columnNames) {
  return {
    columns: columnNames.map((name, index) => ({ id: `col-${index + 1}`, name, cardIds: [] })),
    cards: {},
    nextCardId: 1,
  };
}

function findColumn(state, columnId) {
  const column = state.columns.find((candidate) => candidate.id === columnId);
  if (!column) throw new Error(`Unknown column: ${columnId}`);
  return column;
}

function columnOfCard(state, cardId) {
  const column = state.columns.find((candidate) => candidate.cardIds.includes(cardId));
  if (!column) throw new Error(`Unknown card: ${cardId}`);
  return column;
}

export function addCard(state, columnId, title) {
  const trimmed = title.trim();
  if (!trimmed) throw new Error('Card title is required');
  const column = findColumn(state, columnId);
  const id = `card-${state.nextCardId}`;
  return {
    ...state,
    columns: state.columns.map((col) =>
      col.id === columnId ? { ...col, cardIds: [...col.cardIds, id] } : col
    ),
    cards: { ...state.cards, [id]: { id, title: trimmed } },
    nextCardId: state.nextCardId + 1,
  };
}

export function moveCard(state, cardId, toColumnId, toIndex) {
  const from = columnOfCard(state, cardId);
  const to = findColumn(state, toColumnId);
  const newColumns = state.columns.map((col) => {
    if (col.id === from.id) {
      return { ...col, cardIds: col.cardIds.filter((id) => id !== cardId) };
    }
    if (col.id === to.id) {
      const index = Math.max(0, Math.min(toIndex, col.cardIds.length));
      const newCardIds = [...col.cardIds];
      newCardIds.splice(index, 0, cardId);
      return { ...col, cardIds: newCardIds };
    }
    return col;
  });
  return { ...state, columns: newColumns };
}

export function removeCard(state, cardId) {
  const column = columnOfCard(state, cardId);
  const cards = { ...state.cards };
  delete cards[cardId];
  return {
    ...state,
    columns: state.columns.map((col) =>
      col.id === column.id ? { ...col, cardIds: col.cardIds.filter((id) => id !== cardId) } : col
    ),
    cards,
  };
}

export function renameCard(state, cardId, title) {
  const trimmed = title.trim();
  if (!trimmed) throw new Error('Card title is required');
  if (!state.cards[cardId]) throw new Error(`Unknown card: ${cardId}`);
  return { ...state, cards: { ...state.cards, [cardId]: { id: cardId, title: trimmed } } };
}
