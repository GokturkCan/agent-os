# Order pricing — intended behaviour
All money is integer cents. `priceOrder(items, options)` returns `{ subtotal, discount, shipping, tax, total }`.
- `subtotal` = sum of `unitCents * qty` over items.
- Discount codes: `SAVE10` = 10 %, `SAVE25` = 25 % of the subtotal, computed ONCE on the subtotal and rounded half-up to a whole cent
  (not per line). Unknown or missing code = no discount. Codes are case-insensitive and trimmed.
- Shipping: 0 when (subtotal - discount) >= 5000, else 499. An empty order ships for 0.
- Tax: 8 % of (subtotal - discount), rounded half-up, unless `options.taxExempt` is true (then 0).
- `total` = subtotal - discount + shipping + tax.
- Calls are independent: one call's options never affect another call.
`paginate(list, page, size)`: page is 1-based; returns the items of that page. `size` must be a positive integer or a RangeError is thrown. A page past the end returns [].
`formatMoney(cents)`: `"$12.05"`, negative values `"-$0.99"`.
