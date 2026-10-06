const PERCENT_OFF = { code: 'SAVE10', rate: 0.1, maximumCents: 5000 };
const AMOUNT_OFF = { code: 'TAKE500', amountCents: 500, minimumSubtotalCents: 2500 };
const FREE_SHIPPING = 'FREESHIP';

function normalize(coupon) {
  return coupon == null ? null : coupon.trim().toUpperCase();
}

export function couponDiscount(subtotalCents, coupon) {
  const code = normalize(coupon);
  let discount = 0;
  if (code === PERCENT_OFF.code) {
    discount = Math.min(Math.round(subtotalCents * PERCENT_OFF.rate), PERCENT_OFF.maximumCents);
  } else if (code === AMOUNT_OFF.code && subtotalCents >= AMOUNT_OFF.minimumSubtotalCents) {
    discount = AMOUNT_OFF.amountCents;
  }
  return Math.min(discount, subtotalCents);
}

export function waivesShipping(coupon) {
  return normalize(coupon) === FREE_SHIPPING;
}
