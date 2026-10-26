import test from 'node:test';
import assert from 'node:assert/strict';
import { TtlLruCache } from '../src/cache.ts';

test('set/get basic', () => {
  const c = new TtlLruCache<string, number>({ maxSize: 2, ttlMs: 1000 });
  c.set('a', 1);
  assert.equal(c.get('a'), 1);
});
test('evicts least recently used', () => {
  const c = new TtlLruCache<string, number>({ maxSize: 2, ttlMs: 1000 });
  c.set('a', 1).set('b', 2).set('c', 3);
  assert.equal(c.has('a'), false);
  assert.equal(c.size, 2);
});
