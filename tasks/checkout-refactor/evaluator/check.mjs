// Hidden acceptance checks. cases.json holds what the original calculateOrder returned for
// each order; the module expectations follow from the prompt's table and that same behaviour.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const checks = [];
const load = (file) => import(pathToFileURL(path.resolve(file)).href);
const cases = JSON.parse(readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), 'cases.json'), 'utf8'));

async function check(name, body) {
  try {
    await body();
    checks.push({ name, passed: true });
  } catch (error) {
    checks.push({ name, passed: false, detail: String(error?.message ?? error).slice(0, 400) });
  }
}

for (const [group, list] of Object.entries(cases)) {
  await check(`calculateOrder is unchanged: ${group}`, async () => {
    const { calculateOrder } = await load('src/checkout.js');
    for (const { order, expected } of list) {
      const actual = JSON.parse(JSON.stringify(calculateOrder(structuredClone(order))));
      assert.deepEqual(actual, expected, JSON.stringify(order));
    }
  });
}

const item = (unitPriceCents, quantity, category = 'kitchen') => ({ sku: 'X', unitPriceCents, quantity, category });

await check('lineTotal', async () => {
  const { lineTotal } = await load('src/pricing/lines.js');
  const expected = [[item(333, 1), 333], [item(333, 9), 2997], [item(333, 10), 3163], [item(333, 49), 15501],
    [item(333, 50), 14652], [item(333, 50, 'clearance'), 16650], [item(1999, 10), 18990], [item(1, 10), 9]];
  for (const [input, cents] of expected) assert.equal(lineTotal(input), cents, JSON.stringify(input));
});

await check('couponDiscount', async () => {
  const { couponDiscount } = await load('src/pricing/coupons.js');
  const expected = [[3000, 'SAVE10', 300], [3000, ' save10 ', 300], [15, 'SAVE10', 2], [50001, 'SAVE10', 5000],
    [90000, 'SAVE10', 5000], [2499, 'TAKE500', 0], [2500, 'TAKE500', 500], [9000, 'take500', 500],
    [3000, 'FREESHIP', 0], [3000, 'BOGUS', 0], [3000, '', 0], [3000, null, 0], [0, 'SAVE10', 0]];
  for (const [subtotal, coupon, cents] of expected) {
    assert.equal(couponDiscount(subtotal, coupon), cents, `${subtotal} ${JSON.stringify(coupon)}`);
  }
});

await check('waivesShipping', async () => {
  const { waivesShipping } = await load('src/pricing/coupons.js');
  for (const coupon of ['FREESHIP', 'freeship', '  FreeShip ']) assert.equal(waivesShipping(coupon), true, coupon);
  for (const coupon of ['SAVE10', 'TAKE500', 'BOGUS', '', null]) assert.equal(waivesShipping(coupon), false, String(coupon));
});

await check('shippingCost', async () => {
  const { shippingCost } = await load('src/pricing/shipping.js');
  const cost = (discountedSubtotalCents, region, express = false, coupon = null) =>
    shippingCost({ discountedSubtotalCents, region, express, coupon });
  assert.equal(cost(4999, 'US-CA'), 799);
  assert.equal(cost(5000, 'US-CA'), 399);
  assert.equal(cost(9999, 'US-NY'), 399);
  assert.equal(cost(10000, 'US-NY'), 0);
  assert.equal(cost(2000, 'US-OR', true), 2299);
  assert.equal(cost(2000, 'US-OR', false, 'FREESHIP'), 0);
  assert.equal(cost(2000, 'US-OR', true, ' freeship'), 1500);
  assert.equal(cost(2000, 'JP', false, 'SAVE10'), 799);
  assert.equal(cost(2000, 'EU-DE'), 1999);
  assert.equal(cost(12000, 'EU-FR'), 1200);
  assert.equal(cost(2000, 'EU-FR', false, 'FREESHIP'), 1200);
  assert.equal(cost(7000, 'EU-DE', true, 'FREESHIP'), 2700);
  assert.equal(cost(7000, 'EU-DE', true), 3099);
});

await check('taxFor', async () => {
  const { taxFor } = await load('src/pricing/tax.js');
  const tax = (discountedSubtotalCents, shippingCents, region) => taxFor({ discountedSubtotalCents, shippingCents, region });
  assert.equal(tax(10000, 399, 'US-CA'), 725);
  assert.equal(tax(6789, 0, 'US-CA'), 492);
  assert.equal(tax(6789, 799, 'US-NY'), 603);
  assert.equal(tax(10000, 799, 'US-OR'), 0);
  assert.equal(tax(10000, 799, 'JP'), 0);
  assert.equal(tax(1000, 799, 'EU-DE'), 342);
  assert.equal(tax(1000, 0, 'EU-DE'), 190);
  assert.equal(tax(1234, 1999, 'EU-FR'), 647);
  assert.equal(tax(0, 0, 'EU-FR'), 0);
});

// Comments are not code, so mentions inside them do not count.
const code = () => readFileSync('src/checkout.js', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

await check('checkout.js imports all four pricing modules', () => {
  const source = code();
  for (const name of ['lines', 'coupons', 'shipping', 'tax']) {
    assert.match(source, new RegExp(`from\\s*['"]\\./pricing/${name}\\.js['"]`), `import of pricing/${name}.js`);
  }
});

await check('checkout.js holds no rates, thresholds, fees or coupon codes', () => {
  const source = code();
  const numbers = source.match(/\b\d+(\.\d+)?\b/g) ?? [];
  const forbidden = ['0.12', '0.05', '0.1', '0.0725', '0.08875', '0.19', '0.2', '799', '399', '1200', '1500',
    '5000', '10000', '2500', '500'];
  assert.deepEqual(numbers.filter((number) => forbidden.includes(number)), []);
  assert.doesNotMatch(source, /SAVE10|TAKE500|FREESHIP/i);
});

writeFileSync(path.join(process.env.HB_OUT, 'result.json'), JSON.stringify({ checks }, null, 2));
