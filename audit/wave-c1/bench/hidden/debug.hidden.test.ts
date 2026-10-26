import test from 'node:test';
import assert from 'node:assert/strict';
import { paginate, priceOrder, formatMoney } from '../src/pricing.ts';
const it1 = (u: number, q = 1) => ({ sku: 'x' + u, unitCents: u, qty: q });
test('H1 paginate pages', () => {
  const l = [1, 2, 3, 4, 5, 6, 7];
  assert.deepEqual(paginate(l, 1, 3), [1, 2, 3]);
  assert.deepEqual(paginate(l, 2, 3), [4, 5, 6]);
  assert.deepEqual(paginate(l, 3, 3), [7]);
  assert.deepEqual(paginate(l, 4, 3), []);
});
test('H2 paginate size validation', () => {
  assert.throws(() => paginate([1], 1, 0), RangeError);
  assert.throws(() => paginate([1], 1, -2), RangeError);
  assert.throws(() => paginate([1], 1, 1.5), RangeError);
});
test('H3 discount rounded once on subtotal not per line', () => {
  // three lines of 15c with SAVE10: per-line rounding gives 2+2+2=6 (1.5 rounds up each), once on 45c gives round(4.5)=5
  const r = priceOrder([it1(15), it1(15), it1(15)], { code: 'SAVE10' });
  assert.equal(r.subtotal, 45);
  assert.equal(r.discount, 5);
});
test('H4 discount case-insensitive and trimmed, unknown ignored', () => {
  assert.equal(priceOrder([it1(10000)], { code: ' save25 ' }).discount, 2500);
  assert.equal(priceOrder([it1(10000)], { code: 'NOPE' }).discount, 0);
  assert.equal(priceOrder([it1(10000)]).discount, 0);
});
test('H5 options do not leak between calls', () => {
  const a = priceOrder([it1(10000)], { taxExempt: true });
  assert.equal(a.tax, 0);
  const b = priceOrder([it1(10000)]);
  assert.equal(b.tax, 800);
  const c = priceOrder([it1(10000)], { code: 'SAVE10' });
  assert.equal(c.discount, 1000);
  const d = priceOrder([it1(10000)]);
  assert.equal(d.discount, 0);
});
test('H6 shipping rules', () => {
  assert.equal(priceOrder([]).shipping, 0);
  assert.equal(priceOrder([it1(4999)]).shipping, 499);
  assert.equal(priceOrder([it1(5000)]).shipping, 0);
  // discount can push net under the free-shipping line
  assert.equal(priceOrder([it1(5500)], { code: 'SAVE10' }).shipping, 499);
});
test('H7 tax and total', () => {
  const r = priceOrder([it1(1000, 3)], { code: 'SAVE25' });
  // subtotal 3000, discount 750, net 2250, shipping 499, tax round(180)=180
  assert.deepEqual(r, { subtotal: 3000, discount: 750, shipping: 499, tax: 180, total: 3000 - 750 + 499 + 180 });
  const odd = priceOrder([it1(1, 1)], {});
  assert.equal(odd.tax, 0); // round(0.08)=0
  assert.equal(priceOrder([it1(1250)]).tax, 100);
  assert.equal(priceOrder([it1(1255)]).tax, 100); // 100.4 -> 100
  assert.equal(priceOrder([it1(1257)]).tax, 101); // 100.56 -> 101
});
test('H8 formatMoney', () => {
  assert.equal(formatMoney(0), '$0.00');
  assert.equal(formatMoney(5), '$0.05');
  assert.equal(formatMoney(100000), '$1000.00');
  assert.equal(formatMoney(-1205), '-$12.05');
});
test('H9 does not mutate inputs', () => {
  const items = [it1(2000, 2)]; const snap = JSON.stringify(items);
  priceOrder(items, { code: 'SAVE10' });
  assert.equal(JSON.stringify(items), snap);
});
