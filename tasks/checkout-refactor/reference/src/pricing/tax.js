// Sales tax applies to goods only; VAT also applies to shipping.
const RATES = {
  'US-CA': { rate: 0.0725, taxesShipping: false },
  'US-NY': { rate: 0.08875, taxesShipping: false },
  'EU-DE': { rate: 0.19, taxesShipping: true },
  'EU-FR': { rate: 0.2, taxesShipping: true },
};

export function taxFor({ discountedSubtotalCents, shippingCents, region }) {
  const rule = RATES[region];
  if (!rule) return 0;
  return Math.round((discountedSubtotalCents + (rule.taxesShipping ? shippingCents : 0)) * rule.rate);
}
