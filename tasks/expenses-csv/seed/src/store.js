// In-memory list of expenses.

import { CATEGORIES, createExpense } from './model.js';

export function createStore() {
  const expenses = [];

  function all() {
    return expenses
      .map((expense, position) => ({ expense, position }))
      .sort((a, b) => a.expense.date.localeCompare(b.expense.date) || a.position - b.position)
      .map(({ expense }) => expense);
  }

  return {
    add(fields) {
      const expense = createExpense(fields);
      expenses.push(expense);
      return expense;
    },
    remove(expense) {
      const index = expenses.indexOf(expense);
      if (index === -1) return false;
      expenses.splice(index, 1);
      return true;
    },
    all,
    totalByCategory() {
      const totals = Object.fromEntries(CATEGORIES.map((category) => [category, 0]));
      for (const expense of expenses) totals[expense.category] += expense.amountCents;
      return totals;
    },
  };
}
