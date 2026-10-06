# Expenses

A small expense tracker. No dependencies; open `index.html` through any static server.

- `src/model.js`: `createExpense({ date, category, amountCents, note })` validates and returns an expense. Money is always an integer number of cents. `CATEGORIES` lists the allowed categories.
- `src/store.js`: `createStore()` returns `{ add, remove, all, totalByCategory }`. `all()` returns expenses sorted by date, oldest first; expenses on the same date keep the order they were added in.
- `src/format.js`: `formatMoney(cents)` for display, such as `$1,234.50`.
- `src/view.js`: `renderTable(expenses)` returns the table as an HTML string.
