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

// Returns new columns with `change` applied to a copy of each column's card list.
function withCardIds(state, change) {
  return state.columns.map((column) => ({ ...column, cardIds: change(column.id, [...column.cardIds]) }));
}

export function addCard(state, columnId, title) {
  const trimmed = title.trim();
  if (!trimmed) throw new Error('Card title is required');
  findColumn(state, columnId);
  const id = `card-${state.nextCardId}`;
  return {
    ...state,
    columns: withCardIds(state, (current, cardIds) => (current === columnId ? [...cardIds, id] : cardIds)),
    cards: { ...state.cards, [id]: { id, title: trimmed } },
    nextCardId: state.nextCardId + 1,
  };
}

export function moveCard(state, cardId, toColumnId, toIndex) {
  columnOfCard(state, cardId);
  findColumn(state, toColumnId);
  const without = withCardIds(state, (current, cardIds) => cardIds.filter((id) => id !== cardId));
  const columns = without.map((column) => {
    if (column.id !== toColumnId) return column;
    const index = Math.max(0, Math.min(toIndex, column.cardIds.length));
    return { ...column, cardIds: [...column.cardIds.slice(0, index), cardId, ...column.cardIds.slice(index)] };
  });
  return { ...state, columns };
}

export function removeCard(state, cardId) {
  columnOfCard(state, cardId);
  const cards = { ...state.cards };
  delete cards[cardId];
  return {
    ...state,
    columns: withCardIds(state, (current, cardIds) => cardIds.filter((id) => id !== cardId)),
    cards,
  };
}

export function renameCard(state, cardId, title) {
  const trimmed = title.trim();
  if (!trimmed) throw new Error('Card title is required');
  if (!state.cards[cardId]) throw new Error(`Unknown card: ${cardId}`);
  return { ...state, cards: { ...state.cards, [cardId]: { id: cardId, title: trimmed } } };
}
