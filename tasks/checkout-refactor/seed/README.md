# Checkout

Order pricing for a small shop. All money is an integer number of cents.

`calculateOrder(order)` in `src/checkout.js` takes

```js
{
  items: [{ sku: 'MUG', unitPriceCents: 1200, quantity: 2, category: 'kitchen' }],
  coupon: 'SAVE10',   // or null
  region: 'US-CA',
  express: false,
}
```

and returns `{ lines, subtotalCents, discountCents, shippingCents, taxCents, totalCents }`, where `lines` is `[{ sku, totalCents }]`.

The function grew one rule at a time and is overdue for a clean-up.
