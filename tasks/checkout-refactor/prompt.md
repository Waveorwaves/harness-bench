`calculateOrder` in `src/checkout.js` works, but every pricing rule lives in one long function. Refactor it into small modules without changing what it returns.

## Target structure

| File | Export | Returns |
|---|---|---|
| `src/pricing/lines.js` | `lineTotal(item)` | the line's total in cents after any bulk discount |
| `src/pricing/coupons.js` | `couponDiscount(subtotalCents, coupon)` | the discount in cents; `0` for no coupon, an unknown coupon, or a coupon that does not reduce the price |
| `src/pricing/coupons.js` | `waivesShipping(coupon)` | `true` when the coupon removes the standard shipping charge |
| `src/pricing/shipping.js` | `shippingCost({ discountedSubtotalCents, region, express, coupon })` | shipping in cents for an order that has at least one line |
| `src/pricing/tax.js` | `taxFor({ discountedSubtotalCents, shippingCents, region })` | tax in cents |

`discountedSubtotalCents` is the subtotal minus the coupon discount. `coupon` is the raw value from the order (a string or `null`), so these functions handle its case and spacing themselves.

## Requirements

- `calculateOrder(order)` stays exported from `src/checkout.js` and returns exactly the same result as it does now for every order.
- `src/checkout.js` imports and uses all four pricing modules, and no longer contains any rate, threshold, fee or coupon code itself.
- The existing tests (`npm test`) keep passing. No dependencies.
