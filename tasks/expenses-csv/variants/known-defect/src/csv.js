// CSV export and import for expenses.

import { createExpense } from './model.js';

export function toCsv(expenses) {
  let result = 'date,category,amount,note\n';

  for (const expense of expenses) {
    const fields = [
      expense.date,
      expense.category,
      (expense.amountCents / 100).toFixed(2),
      expense.note,
    ];

    const csvLine = fields
      .map((field) => quoteCsvField(field.toString()))
      .join(',');

    result += csvLine + '\n';
  }

  return result;
}

function quoteCsvField(field) {
  // A field is wrapped in double quotes only when it contains a comma, a double quote or a line break.
  if (field.includes(',') || field.includes('"') || field.includes('\n') || field.includes('\r')) {
    // Inside quotes, a double quote is written twice.
    return '"' + field.replace(/"/g, '""') + '"';
  }
  return field;
}

export function fromCsv(text) {
  const lines = text.split(/\r?\n/);
  const expenses = [];
  const errors = [];

  // Check header
  if (lines.length === 0 || lines[0] !== 'date,category,amount,note') {
    errors.push({ line: 1, message: 'Invalid header' });
    return { expenses, errors };
  }

  let i = 1;

  while (i < lines.length) {
    // Skip empty lines
    if (lines[i].trim() === '') {
      i++;
      continue;
    }

    const result = parseCsvLine(lines, i);
    if (!result) {
      errors.push({ line: i + 1, message: 'Unclosed quoted field' });
      i++;
      continue;
    }

    const { fields, nextIndex } = result;
    const rowLineNumber = i + 1;  // line numbers are 1-based
    i = nextIndex;

    if (fields.length !== 4) {
      errors.push({ line: rowLineNumber, message: 'Expected 4 fields' });
      continue;
    }

    const [date, category, amountStr, note] = fields;

    // Validate and convert amount
    const amountMatch = amountStr.match(/^(\d+)(?:\.(\d{1,2}))?$/);
    if (!amountMatch) {
      errors.push({ line: rowLineNumber, message: 'Invalid amount format' });
      continue;
    }

    const dollars = parseInt(amountMatch[1]);
    const cents = amountMatch[2] ? parseInt(amountMatch[2].padEnd(2, '0')) : 0;
    const amountCents = dollars * 100 + cents;

    // Try to create the expense
    try {
      const expense = createExpense({ date, category, amountCents, note });
      expenses.push(expense);
    } catch (err) {
      errors.push({ line: rowLineNumber, message: err.message });
    }
  }

  return { expenses, errors };
}

function parseCsvLine(lines, startIndex) {
  let i = startIndex;
  const fields = [];
  let currentField = '';
  let inQuotes = false;
  let lineNum = startIndex;

  while (i < lines.length) {
    const line = lines[i];
    let charIndex = 0;

    while (charIndex < line.length) {
      const char = line[charIndex];

      if (inQuotes) {
        if (char === '"') {
          if (charIndex + 1 < line.length && line[charIndex + 1] === '"') {
            // Escaped double quote
            currentField += '"';
            charIndex += 2;
          } else {
            // End of quoted field
            inQuotes = false;
            charIndex++;
          }
        } else {
          currentField += char;
          charIndex++;
        }
      } else {
        if (char === '"') {
          inQuotes = true;
          charIndex++;
        } else if (char === ',') {
          fields.push(currentField);
          currentField = '';
          charIndex++;
        } else {
          currentField += char;
          charIndex++;
        }
      }
    }

    if (inQuotes) {
      // Continue to next line
      currentField += '\n';
      i++;
    } else {
      // End of line, add the last field
      fields.push(currentField);
      return { fields, nextIndex: i + 1 };
    }
  }

  // If we're still in quotes at the end, it's an error
  if (inQuotes) {
    return null;
  }

  if (currentField.length > 0 || fields.length > 0) {
    fields.push(currentField);
    return { fields, nextIndex: i };
  }

  return null;
}
