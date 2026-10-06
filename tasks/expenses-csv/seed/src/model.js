// What an expense is and what makes one valid.

export const CATEGORIES = ['food', 'transport', 'housing', 'fun', 'other'];

export function isValidDate(text) {
  if (typeof text !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  const date = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === text;
}

export function createExpense({ date, category, amountCents, note = '' }) {
  if (!isValidDate(date)) throw new Error(`Invalid date: ${date}`);
  if (!CATEGORIES.includes(category)) throw new Error(`Unknown category: ${category}`);
  if (!Number.isInteger(amountCents) || amountCents <= 0) throw new Error(`Invalid amount: ${amountCents}`);
  if (typeof note !== 'string' || note.length > 200) throw new Error('Note must be text of at most 200 characters');
  return { date, category, amountCents, note };
}
