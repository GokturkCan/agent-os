import test from 'node:test';
import assert from 'node:assert/strict';
import { TtlLruCache } from '../src/cache.ts';
const mk = (o: any = {}) => { let t = 1000; const clock = { now: () => t, adv: (n: number) => { t += n; } }; const ev: any[] = []; const c = new TtlLruCache<string, any>({ maxSize: 3, ttlMs: 100, now: clock.now, onEvict: (k, v, r) => ev.push([k, v, r]), ...o }); return { c, clock, ev }; };
test('T1 validation', () => {
  for (const bad of [0, -1, 1.5, NaN]) assert.throws(() => new TtlLruCache({ maxSize: bad as any, ttlMs: 10 }), RangeError);
  for (const bad of [0, -5, Infinity, NaN]) assert.throws(() => new TtlLruCache({ maxSize: 1, ttlMs: bad as any }), RangeError);
});
test('T2 expiry boundary is inclusive of ttl', () => {
  const { c, clock } = mk(); c.set('a', 1); clock.adv(99); assert.equal(c.get('a'), 1); clock.adv(1); assert.equal(c.get('a'), undefined);
});
test('T3 get refreshes recency but not ttl', () => {
  const { c, clock } = mk(); c.set('a', 1); clock.adv(60); c.get('a'); clock.adv(40); assert.equal(c.has('a'), false);
});
test('T4 set restarts ttl and recency', () => {
  const { c, clock, ev } = mk(); c.set('a', 1); clock.adv(90); c.set('a', 2); clock.adv(90); assert.equal(c.get('a'), 2); assert.deepEqual(ev, []);
});
test('T5 capacity eviction order honours get recency, reports capacity', () => {
  const { c, ev } = mk(); c.set('a', 1).set('b', 2).set('c', 3); c.get('a'); c.set('d', 4);
  assert.deepEqual(ev, [['b', 2, 'capacity']]); assert.equal(c.has('b'), false); assert.equal(c.has('a'), true);
});
test('T6 peek changes neither recency nor ttl', () => {
  const { c, clock, ev } = mk(); c.set('a', 1).set('b', 2).set('c', 3); assert.equal(c.peek('a'), 1); c.set('d', 4);
  assert.deepEqual(ev, [['a', 1, 'capacity']]); clock.adv(100); assert.equal(c.peek('b'), undefined);
});
test('T7 has does not change recency', () => {
  const { c, ev } = mk(); c.set('a', 1).set('b', 2).set('c', 3); assert.equal(c.has('a'), true); c.set('d', 4);
  assert.deepEqual(ev, [['a', 1, 'capacity']]);
});
test('T8 size purges expired and reports them', () => {
  const { c, clock, ev } = mk(); c.set('a', 1).set('b', 2); clock.adv(50); c.set('c', 3); clock.adv(50);
  assert.equal(c.size, 1); assert.deepEqual(ev.map((e) => [e[0], e[2]]).sort(), [['a', 'expired'], ['b', 'expired']]);
});
test('T9 delete semantics', () => {
  const { c, clock, ev } = mk(); c.set('a', 1).set('b', 2);
  assert.equal(c.delete('a'), true); assert.equal(c.delete('a'), false); assert.deepEqual(ev, []);
  clock.adv(100); assert.equal(c.delete('b'), false); assert.deepEqual(ev, [['b', 2, 'expired']]);
});
test('T10 overwrite does not call onEvict', () => {
  const { c, ev } = mk(); c.set('a', 1); c.set('a', 2); assert.deepEqual(ev, []); assert.equal(c.size, 1);
});
test('T11 purgeExpired returns count', () => {
  const { c, clock } = mk(); c.set('a', 1).set('b', 2); clock.adv(100); assert.equal(c.purgeExpired(), 2); assert.equal(c.purgeExpired(), 0);
});
test('T12 undefined is a legal value', () => {
  const { c } = mk(); c.set('u', undefined); assert.equal(c.has('u'), true); assert.equal(c.get('u'), undefined); assert.equal(c.size, 1);
});
test('T13 throwing onEvict keeps state consistent and propagates', () => {
  let boom = true; const { c } = mk({ maxSize: 1, onEvict: () => { if (boom) throw new Error('x'); } });
  c.set('a', 1); assert.throws(() => c.set('b', 2), /x/); boom = false;
  assert.equal(c.size, 1); assert.equal(c.has('b'), true); assert.equal(c.has('a'), false); c.set('c', 3); assert.equal(c.size, 1);
});
test('T14 expired entries do not consume capacity', () => {
  const { c, clock, ev } = mk(); c.set('a', 1).set('b', 2).set('c', 3); clock.adv(100); c.set('d', 4);
  assert.equal(ev.filter((e) => e[2] === 'capacity').length, 0); assert.equal(c.size, 1);
});
test('T15 many ops stay within maxSize', () => {
  const { c } = mk({ maxSize: 5 }); for (let i = 0; i < 1000; i++) { c.set('k' + (i % 17), i); assert.ok(c.size <= 5); }
});
