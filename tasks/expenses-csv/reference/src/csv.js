// CSV export and import for expenses.

import { createExpense } from './model.js';

const HEADER = 'date,category,amount,note';

function quote(field) {
  return /[",\r\n]/.test(field) ? `"${field.replace(/"/g, '""')}"` : field;
}

function dollars(cents) {
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
}

export function toCsv(expenses) {
  const rows = expenses.map((expense) => [expense.date, expense.category, dollars(expense.amountCents), expense.note]
    .map(quote).join(','));
  return [HEADER, ...rows].map((row) => `${row}\n`).join('');
}

function cents(text) {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(text);
  if (!match) throw new Error(`Invalid amount: ${text}`);
  return Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'));
}

// Splits text into rows of fields, remembering the line each row starts on.
function parseRows(text) {
  const rows = [];
  let fields = [];
  let field = '';
  let quoted = false;
  let line = 1;
  let startLine = 1;
  let touched = false;
  const endRow = () => {
    if (touched) rows.push({ line: startLine, fields: [...fields, field] });
    fields = [];
    field = '';
    touched = false;
  };
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (!touched && character !== '\n' && character !== '\r') {
      touched = true;
      startLine = line;
    }
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') quoted = false;
      else {
        if (character === '\n') line += 1;
        field += character;
      }
    } else if (character === '"') quoted = true;
    else if (character === ',') {
      fields.push(field);
      field = '';
    } else if (character === '\n' || character === '\r') {
      if (character === '\r' && text[index + 1] === '\n') index += 1;
      endRow();
      line += 1;
    } else field += character;
  }
  endRow();
  return rows;
}

export function fromCsv(text) {
  const firstLine = text.split(/\r?\n/, 1)[0];
  if (firstLine !== HEADER) return { expenses: [], errors: [{ line: 1, message: 'Missing header' }] };
  const expenses = [];
  const errors = [];
  for (const { line, fields } of parseRows(text).slice(1)) {
    try {
      if (fields.length !== 4) throw new Error(`Expected 4 fields but found ${fields.length}`);
      const [date, category, amount, note] = fields;
      expenses.push(createExpense({ date, category, amountCents: cents(amount), note }));
    } catch (error) {
      errors.push({ line, message: error.message });
    }
  }
  return { expenses, errors };
}
