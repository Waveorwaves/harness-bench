import assert from 'node:assert/strict';
import test from 'node:test';

import { calculateOrder } from '../src/checkout.js';

const mug = (quantity) => ({ sku: 'MUG', unitPriceCents: 1200, quantity, category: 'kitchen' });

test('a plain order', () => {
  assert.deepEqual(calculateOrder({ items: [mug(2)], coupon: null, region: 'US-OR', express: false }), {
    lines: [{ sku: 'MUG', totalCents: 2400 }],
    subtotalCents: 2400,
    discountCents: 0,
    shippingCents: 799,
    taxCents: 0,
    totalCents: 3199,
  });
});

test('bulk discount, coupon and tax', () => {
  const result = calculateOrder({ items: [mug(10)], coupon: 'save10', region: 'US-CA', express: false });
  assert.equal(result.subtotalCents, 11400);
  assert.equal(result.discountCents, 1140);
  assert.equal(result.shippingCents, 0);
  assert.equal(result.taxCents, 744);
  assert.equal(result.totalCents, 11004);
});

test('shipping to the EU is taxed', () => {
  const result = calculateOrder({ items: [mug(1)], coupon: 'FREESHIP', region: 'EU-DE', express: true });
  assert.equal(result.shippingCents, 2700);
  assert.equal(result.taxCents, 741);
});
