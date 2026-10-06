Add CSV export and import to this expense tracker. `README.md` describes the existing code.

## `src/csv.js` (new)

`toCsv(expenses)` returns a string:

- The first line is the header `date,category,amount,note`.
- Then one line per expense, in the order given.
- `amount` is in dollars with exactly two decimals and no currency symbol or thousands separator (`1250` cents is `12.50`).
- A field is wrapped in double quotes only when it contains a comma, a double quote or a line break. Inside quotes, a double quote is written twice.
- Every line ends with `\n`, including the last one.

`fromCsv(text)` returns `{ expenses, errors }`:

- Lines may end with `\n` or `\r\n`.
- Quoted fields may contain commas, line breaks and doubled double quotes.
- Empty lines between rows are ignored.
- `amount` must be digits, optionally followed by a dot and one or two digits (`12`, `12.5`, `12.50`). Convert it to cents exactly (`19.99` is `1999`). Anything else is an error.
- Build each row with `createExpense` from `src/model.js`. A row that it rejects, has a bad amount, or does not have exactly four fields is skipped and reported.
- `expenses` holds the valid rows in file order.
- `errors` is an array of `{ line, message }`. `line` is the 1-based line number in `text` where the row starts (the header is line 1). `message` is any non-empty string.
- If the first line is not exactly the header, return no expenses and one error for line 1.
- `fromCsv(toCsv(list)).expenses` must equal `list` for any list of valid expenses.

## `src/store.js` (extend)

- `store.exportCsv()` returns `toCsv(store.all())`.
- `store.importCsv(text)` adds every valid row and returns `{ added, errors }`, where `added` is the number of rows added.

No dependencies. The existing tests (`npm test`) must keep passing.
