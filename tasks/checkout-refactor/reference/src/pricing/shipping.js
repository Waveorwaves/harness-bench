import { waivesShipping } from './coupons.js';

const STANDARD_TIERS = [
  { belowCents: 5000, feeCents: 799 },
  { belowCents: 10000, feeCents: 399 },
];
const EU_SURCHARGE_CENTS = 1200;
const EXPRESS_CENTS = 1500;

export const isEu = (region) => region === 'EU-DE' || region === 'EU-FR';

export function shippingCost({ discountedSubtotalCents, region, express, coupon }) {
  const tier = STANDARD_TIERS.find((candidate) => discountedSubtotalCents < candidate.belowCents);
  let cost = waivesShipping(coupon) || !tier ? 0 : tier.feeCents;
  if (isEu(region)) cost += EU_SURCHARGE_CENTS;
  if (express) cost += EXPRESS_CENTS;
  return cost;
}
