import assert from 'node:assert/strict';
import test from 'node:test';

import { formatMoney } from '../src/format.js';
import { createExpense, isValidDate } from '../src/model.js';
import { createStore } from '../src/store.js';
import { renderTable } from '../src/view.js';

test('createExpense validates its fields', () => {
  const expense = createExpense({ date: '2026-03-01', category: 'food', amountCents: 1250, note: 'lunch' });
  assert.deepEqual(expense, { date: '2026-03-01', category: 'food', amountCents: 1250, note: 'lunch' });
  assert.throws(() => createExpense({ date: '2026-02-30', category: 'food', amountCents: 1 }));
  assert.throws(() => createExpense({ date: '2026-03-01', category: 'pets', amountCents: 1 }));
  assert.throws(() => createExpense({ date: '2026-03-01', category: 'food', amountCents: 12.5 }));
  assert.equal(isValidDate('2024-02-29'), true);
});

test('store sorts by date and totals by category', () => {
  const store = createStore();
  store.add({ date: '2026-03-02', category: 'food', amountCents: 500 });
  const first = store.add({ date: '2026-03-01', category: 'fun', amountCents: 2000 });
  store.add({ date: '2026-03-02', category: 'food', amountCents: 250, note: 'coffee' });
  assert.deepEqual(store.all().map((expense) => expense.amountCents), [2000, 500, 250]);
  assert.equal(store.totalByCategory().food, 750);
  assert.equal(store.remove(first), true);
  assert.equal(store.all().length, 2);
});

test('formatMoney and renderTable', () => {
  assert.equal(formatMoney(123450), '$1,234.50');
  assert.equal(formatMoney(5), '$0.05');
  const html = renderTable([createExpense({ date: '2026-03-01', category: 'food', amountCents: 5, note: '<b>' })]);
  assert.ok(html.includes('&lt;b&gt;') && html.includes('$0.05'));
});
