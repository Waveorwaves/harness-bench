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
  column.cardIds.push(id);
  return {
    ...state,
    cards: { ...state.cards, [id]: { id, title: trimmed } },
    nextCardId: state.nextCardId + 1,
  };
}

export function moveCard(state, cardId, toColumnId, toIndex) {
  const from = columnOfCard(state, cardId);
  const to = findColumn(state, toColumnId);
  from.cardIds.splice(from.cardIds.indexOf(cardId), 1);
  const index = Math.max(0, Math.min(toIndex, to.cardIds.length));
  to.cardIds.splice(index, 0, cardId);
  return { ...state };
}

export function removeCard(state, cardId) {
  const column = columnOfCard(state, cardId);
  column.cardIds.splice(column.cardIds.indexOf(cardId), 1);
  const cards = { ...state.cards };
  delete cards[cardId];
  return { ...state, cards };
}

export function renameCard(state, cardId, title) {
  const trimmed = title.trim();
  if (!trimmed) throw new Error('Card title is required');
  if (!state.cards[cardId]) throw new Error(`Unknown card: ${cardId}`);
  return { ...state, cards: { ...state.cards, [cardId]: { id: cardId, title: trimmed } } };
}
