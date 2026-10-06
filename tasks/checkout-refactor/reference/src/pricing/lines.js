const BULK_TIERS = [
  { minimumQuantity: 50, rate: 0.12 },
  { minimumQuantity: 10, rate: 0.05 },
];

export function lineTotal(item) {
  const full = item.unitPriceCents * item.quantity;
  if (item.category === 'clearance') return full;
  const tier = BULK_TIERS.find((candidate) => item.quantity >= candidate.minimumQuantity);
  return tier ? full - Math.round(full * tier.rate) : full;
}
