// Renders the board as HTML.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };

export function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (character) => ESCAPES[character]);
}

function renderCard(card) {
  return `<li class="card" draggable="true" data-id="${card.id}">${escapeHtml(card.title)}</li>`;
}

function renderColumn(state, column) {
  const cards = column.cardIds.map((id) => renderCard(state.cards[id])).join('');
  return `<section class="column" data-id="${column.id}"><h2>${escapeHtml(column.name)}</h2>`
    + `<ul class="cards">${cards}</ul>`
    + `<form class="add"><input name="title" aria-label="New card in ${escapeHtml(column.name)}"><button>Add</button></form>`
    + '</section>';
}

export function renderBoard(state) {
  return `<div class="board">${state.columns.map((column) => renderColumn(state, column)).join('')}</div>`;
}
