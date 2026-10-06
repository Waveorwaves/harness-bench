// Display formatting.

export function formatMoney(cents) {
  const sign = cents < 0 ? '-' : '';
  const absolute = Math.abs(cents);
  const dollars = Math.floor(absolute / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${sign}$${dollars}.${String(absolute % 100).padStart(2, '0')}`;
}
