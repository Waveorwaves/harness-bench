// Renders the expense table as HTML.

import { formatMoney } from './format.js';

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
const escapeHtml = (text) => String(text).replace(/[&<>"]/g, (character) => ESCAPES[character]);

export function renderTable(expenses) {
  const rows = expenses.map((expense) => '<tr>'
    + `<td>${expense.date}</td><td>${escapeHtml(expense.category)}</td>`
    + `<td class="amount">${formatMoney(expense.amountCents)}</td><td>${escapeHtml(expense.note)}</td>`
    + '</tr>').join('');
  return `<table><thead><tr><th>Date</th><th>Category</th><th>Amount</th><th>Note</th></tr></thead><tbody>${rows}</tbody></table>`;
}
