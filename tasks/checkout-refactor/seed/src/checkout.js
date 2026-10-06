export function calculateOrder(order) {
  var lines = [];
  var subtotal = 0;
  for (var i = 0; i < order.items.length; i++) {
    var it = order.items[i];
    if (it.quantity <= 0) {
      continue;
    }
    var t = it.unitPriceCents * it.quantity;
    if (it.category != 'clearance') {
      if (it.quantity >= 50) {
        t = t - Math.round(t * 0.12);
      } else {
        if (it.quantity >= 10) {
          t = t - Math.round(t * 0.05);
        }
      }
    }
    lines.push({ sku: it.sku, totalCents: t });
    subtotal = subtotal + t;
  }

  // coupons
  var discount = 0;
  var freeShip = false;
  var code = order.coupon;
  if (code != null) {
    code = code.trim().toUpperCase();
    if (code == 'SAVE10') {
      discount = Math.round(subtotal * 0.1);
      if (discount > 5000) {
        discount = 5000;
      }
    } else if (code == 'TAKE500') {
      if (subtotal >= 2500) {
        discount = 500;
      }
    } else if (code == 'FREESHIP') {
      freeShip = true;
    }
  }
  if (discount > subtotal) {
    discount = subtotal;
  }
  var after = subtotal - discount;

  // shipping
  var shipping = 0;
  if (lines.length > 0) {
    if (order.region == 'EU-DE' || order.region == 'EU-FR') {
      if (after < 5000) {
        shipping = 799;
      } else if (after < 10000) {
        shipping = 399;
      } else {
        shipping = 0;
      }
      if (freeShip) {
        shipping = 0;
      }
      shipping = shipping + 1200;
      if (order.express) {
        shipping = shipping + 1500;
      }
    } else {
      if (after < 5000) {
        shipping = 799;
      } else if (after < 10000) {
        shipping = 399;
      } else {
        shipping = 0;
      }
      if (freeShip) {
        shipping = 0;
      }
      if (order.express) {
        shipping = shipping + 1500;
      }
    }
  }

  // tax
  var tax = 0;
  if (order.region == 'US-CA') {
    tax = Math.round(after * 0.0725);
  } else if (order.region == 'US-NY') {
    tax = Math.round(after * 0.08875);
  } else if (order.region == 'EU-DE') {
    tax = Math.round((after + shipping) * 0.19);
  } else if (order.region == 'EU-FR') {
    tax = Math.round((after + shipping) * 0.2);
  }

  return {
    lines: lines,
    subtotalCents: subtotal,
    discountCents: discount,
    shippingCents: shipping,
    taxCents: tax,
    totalCents: after + shipping + tax,
  };
}
