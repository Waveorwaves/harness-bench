// Hidden acceptance checks. Every expectation is stated in the prompt or the seed's README.
import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const checks = [];
const load = (file) => import(pathToFileURL(path.resolve(file)).href);

async function check(name, body) {
  try {
    await body(await load('src/csv.js').catch(() => ({})));
    checks.push({ name, passed: true });
  } catch (error) {
    checks.push({ name, passed: false, detail: String(error?.message ?? error).slice(0, 400) });
  }
}

const HEADER = 'date,category,amount,note';
const expense = (date, category, amountCents, note = '') => ({ date, category, amountCents, note });
const plain = (value) => JSON.parse(JSON.stringify(value));
const lines = (errors) => errors.map((error) => error.line);

function wellFormed(errors) {
  assert.ok(Array.isArray(errors));
  for (const error of errors) {
    assert.ok(Number.isInteger(error.line), 'error.line is an integer');
    assert.ok(typeof error.message === 'string' && error.message.length > 0, 'error.message is non-empty');
  }
}

await check('toCsv writes the header, rows in order and a final newline', ({ toCsv }) => {
  const text = toCsv([expense('2026-03-02', 'food', 1250, 'lunch'), expense('2026-03-01', 'fun', 2000)]);
  assert.equal(text, `${HEADER}\n2026-03-02,food,12.50,lunch\n2026-03-01,fun,20.00,\n`);
});

await check('toCsv of an empty list is just the header', ({ toCsv }) => {
  assert.equal(toCsv([]), `${HEADER}\n`);
});

await check('toCsv formats amounts with two decimals and no separators', ({ toCsv }) => {
  const text = toCsv([5, 70, 1999, 100000, 123456789].map((cents) => expense('2026-01-05', 'other', cents)));
  assert.deepEqual(text.trimEnd().split('\n').slice(1).map((row) => row.split(',')[2]),
    ['0.05', '0.70', '19.99', '1000.00', '1234567.89']);
});

await check('toCsv quotes only fields that need it', ({ toCsv }) => {
  const text = toCsv([
    expense('2026-01-05', 'food', 100, 'bread, milk'),
    expense('2026-01-05', 'food', 100, 'the "good" one'),
    expense('2026-01-05', 'food', 100, 'two\nlines'),
    expense('2026-01-05', 'food', 100, "it's fine; no quotes here"),
  ]);
  assert.equal(text, `${HEADER}\n`
    + '2026-01-05,food,1.00,"bread, milk"\n'
    + '2026-01-05,food,1.00,"the ""good"" one"\n'
    + '2026-01-05,food,1.00,"two\nlines"\n'
    + "2026-01-05,food,1.00,it's fine; no quotes here\n");
});

await check('fromCsv reads plain rows', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\n2026-03-02,food,12.50,lunch\n2026-03-01,fun,20.00,\n`);
  assert.deepEqual(plain(result.expenses), [expense('2026-03-02', 'food', 1250, 'lunch'), expense('2026-03-01', 'fun', 2000)]);
  assert.deepEqual(result.errors, []);
});

await check('fromCsv accepts windows line endings and a missing final newline', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\r\n2026-03-02,food,12.50,lunch\r\n2026-03-01,fun,20.00,cinema`);
  assert.deepEqual(plain(result.expenses), [expense('2026-03-02', 'food', 1250, 'lunch'), expense('2026-03-01', 'fun', 2000, 'cinema')]);
  assert.deepEqual(result.errors, []);
});

await check('fromCsv reads quoted fields', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\n`
    + '2026-01-05,food,1.00,"bread, milk"\n'
    + '2026-01-05,food,1.00,"the ""good"" one"\n'
    + '2026-01-05,food,1.00,"two\nlines"\n'
    + '"2026-01-06","fun","3.00","all quoted"\n');
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.expenses.map((item) => item.note), ['bread, milk', 'the "good" one', 'two\nlines', 'all quoted']);
  assert.equal(result.expenses[3].amountCents, 300);
});

await check('fromCsv converts amounts to cents exactly', ({ fromCsv }) => {
  const amounts = { 12: 1200, '12.5': 1250, '12.50': 1250, '19.99': 1999, '0.07': 7, '1.15': 115,
    '1234.56': 123456, '4.35': 435, '8.2': 820, '1000000.01': 100000001 };
  const text = `${HEADER}\n${Object.keys(amounts).map((amount) => `2026-01-05,other,${amount},\n`).join('')}`;
  const result = fromCsv(text);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.expenses.map((item) => item.amountCents), Object.values(amounts));
});

await check('fromCsv rejects malformed amounts', ({ fromCsv }) => {
  const bad = ['-5', '0', '1.999', 'abc', '$5', '', '1e2', '1,5', '12.', '0x10'];
  const text = `${HEADER}\n${bad.map((amount) => `2026-01-05,other,${amount.includes(',') ? `"${amount}"` : amount},\n`).join('')}`;
  const result = fromCsv(text);
  assert.deepEqual(result.expenses, []);
  wellFormed(result.errors);
  assert.deepEqual(lines(result.errors), bad.map((_, index) => index + 2));
});

await check('fromCsv skips and reports rows the model rejects', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\n`
    + '2026-01-05,food,1.00,ok\n'
    + '2026-02-30,food,1.00,no such day\n'
    + '2026-01-05,pets,1.00,unknown category\n'
    + '05/01/2026,food,1.00,wrong date format\n'
    + `2026-01-07,food,2.00,${'x'.repeat(201)}\n`
    + '2026-01-06,fun,2.00,also ok\n');
  assert.deepEqual(result.expenses.map((item) => item.note), ['ok', 'also ok']);
  wellFormed(result.errors);
  assert.deepEqual(lines(result.errors), [3, 4, 5, 6]);
});

await check('fromCsv reports rows with the wrong number of fields', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\n2026-01-05,food,1.00\n2026-01-05,food,1.00,a,b\n2026-01-05,food,1.00,fine\n`);
  assert.deepEqual(result.expenses.map((item) => item.note), ['fine']);
  wellFormed(result.errors);
  assert.deepEqual(lines(result.errors), [2, 3]);
});

await check('fromCsv ignores empty lines and still counts them', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\n\n2026-01-05,food,1.00,a\n\n\n2026-01-05,nope,1.00,b\n2026-01-05,food,2.00,c\n\n`);
  assert.deepEqual(result.expenses.map((item) => item.note), ['a', 'c']);
  assert.deepEqual(lines(result.errors), [6]);
});

await check('fromCsv line numbers account for line breaks inside quotes', ({ fromCsv }) => {
  const result = fromCsv(`${HEADER}\n`
    + '2026-01-05,food,1.00,"spans\nthree\nlines"\n'
    + '2026-01-05,food,oops,bad amount\n'
    + '2026-01-05,nope,1.00,"bad category\nover two lines"\n'
    + '2026-13-01,food,1.00,bad date\n');
  assert.equal(result.expenses.length, 1);
  assert.deepEqual(lines(result.errors), [5, 6, 8]);
});

await check('fromCsv requires the header', ({ fromCsv }) => {
  for (const text of ['2026-01-05,food,1.00,a\n', 'Date,Category,Amount,Note\n2026-01-05,food,1.00,a\n', '']) {
    const result = fromCsv(text);
    assert.deepEqual(result.expenses, []);
    wellFormed(result.errors);
    assert.deepEqual(lines(result.errors), [1]);
  }
  for (const text of [`${HEADER}\n`, HEADER, `${HEADER}\r\n`]) {
    const result = fromCsv(text);
    assert.deepEqual(result.expenses, []);
    assert.deepEqual(result.errors, []);
  }
});

await check('export then import returns the same expenses', ({ toCsv, fromCsv }) => {
  const list = [
    expense('2024-02-29', 'housing', 123456, 'rent, "March"\r\nplus fees'),
    expense('2026-01-05', 'food', 1, ''),
    expense('2026-01-05', 'transport', 1999, ' leading and trailing spaces '),
    expense('2026-01-06', 'other', 115, '"'),
    expense('2026-01-07', 'fun', 70, ',,,'),
    expense('2026-01-08', 'fun', 435, 'line one\n\nline three'),
  ];
  const result = fromCsv(toCsv(list));
  assert.deepEqual(result.errors, []);
  assert.deepEqual(plain(result.expenses), list);
});

await check('store exports and imports', async ({ toCsv }) => {
  const { createStore } = await load('src/store.js');
  const store = createStore();
  store.add(expense('2026-03-02', 'food', 500, 'later'));
  store.add(expense('2026-03-01', 'fun', 2000, 'earlier'));
  assert.equal(store.exportCsv(), `${HEADER}\n2026-03-01,fun,20.00,earlier\n2026-03-02,food,5.00,later\n`);
  assert.equal(store.exportCsv(), toCsv(store.all()));
  const outcome = store.importCsv(`${HEADER}\n2026-02-01,food,1.50,imported\n2026-02-01,nope,1.00,bad\n2026-04-01,other,0.99,"last, one"\n`);
  assert.equal(outcome.added, 2);
  assert.deepEqual(lines(outcome.errors), [3]);
  assert.deepEqual(store.all().map((item) => item.note), ['imported', 'earlier', 'later', 'last, one']);
  assert.equal(store.totalByCategory().food, 650);
  assert.equal(store.totalByCategory().other, 99);
});

await check('existing store behaviour is preserved', async () => {
  const { createStore } = await load('src/store.js');
  const store = createStore();
  store.add(expense('2026-03-02', 'food', 500));
  const first = store.add(expense('2026-03-01', 'fun', 2000));
  store.add(expense('2026-03-02', 'food', 250, 'coffee'));
  assert.deepEqual(store.all().map((item) => item.amountCents), [2000, 500, 250]);
  assert.throws(() => store.add(expense('2026-03-01', 'food', 0)));
  assert.equal(store.remove(first), true);
  assert.equal(store.remove(first), false);
  assert.deepEqual(store.totalByCategory(), { food: 750, transport: 0, housing: 0, fun: 0, other: 0 });
});

writeFileSync(path.join(process.env.HB_OUT, 'result.json'), JSON.stringify({ checks }, null, 2));
