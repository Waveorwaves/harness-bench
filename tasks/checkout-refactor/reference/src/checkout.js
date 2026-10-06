import { couponDiscount } from './pricing/coupons.js';
import { lineTotal } from './pricing/lines.js';
import { shippingCost } from './pricing/shipping.js';
import { taxFor } from './pricing/tax.js';

export function calculateOrder(order) {
  const { coupon, region, express } = order;
  const lines = order.items
    .filter((item) => item.quantity > 0)
    .map((item) => ({ sku: item.sku, totalCents: lineTotal(item) }));
  const subtotalCents = lines.reduce((sum, line) => sum + line.totalCents, 0);
  const discountCents = couponDiscount(subtotalCents, coupon);
  const discountedSubtotalCents = subtotalCents - discountCents;
  const shippingCents = lines.length
    ? shippingCost({ discountedSubtotalCents, region, express, coupon })
    : 0;
  const taxCents = taxFor({ discountedSubtotalCents, shippingCents, region });
  return {
    lines,
    subtotalCents,
    discountCents,
    shippingCents,
    taxCents,
    totalCents: discountedSubtotalCents + shippingCents + taxCents,
  };
}
