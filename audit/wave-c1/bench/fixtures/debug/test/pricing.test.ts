import test from 'node:test';
import assert from 'node:assert/strict';
import { paginate, priceOrder, formatMoney } from '../src/pricing.ts';

test('formatMoney basic', () => {
  assert.equal(formatMoney(1205), '$12.05');
  assert.equal(formatMoney(-99), '-$0.99');
});
test('paginate page 1 is the first page', () => {
  assert.deepEqual(paginate([1, 2, 3, 4, 5], 1, 2), [1, 2]);
});
test('paginate last partial page', () => {
  assert.deepEqual(paginate([1, 2, 3, 4, 5], 3, 2), [5]);
});
test('priceOrder simple', () => {
  const r = priceOrder([{ sku: 'a', unitCents: 1000, qty: 2 }]);
  assert.equal(r.subtotal, 2000);
  assert.equal(r.shipping, 499);
});
