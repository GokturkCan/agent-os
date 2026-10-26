export type EvictReason = 'capacity' | 'expired';
export interface CacheOptions<K, V> { maxSize: number; ttlMs: number; now?: () => number; onEvict?: (key: K, value: V, reason: EvictReason) => void }
export class TtlLruCache<K, V> {
  #m = new Map<K, { v: V; at: number }>();
  #o: CacheOptions<K, V>;
  constructor(o: CacheOptions<K, V>) {
    if (!Number.isInteger(o.maxSize) || o.maxSize < 1) throw new RangeError('maxSize');
    if (!Number.isFinite(o.ttlMs) || o.ttlMs <= 0) throw new RangeError('ttlMs');
    this.#o = { ...o, now: o.now ?? Date.now };
  }
  #dead(e: { at: number }) { return this.#o.now!() >= e.at + this.#o.ttlMs; }
  #drop(k: K, reason: EvictReason) { const e = this.#m.get(k)!; this.#m.delete(k); this.#o.onEvict?.(k, e.v, reason); }
  purgeExpired(): number { let n = 0; for (const [k, e] of [...this.#m]) if (this.#dead(e)) { n++; this.#drop(k, 'expired'); } return n; }
  set(k: K, v: V): this {
    this.#m.delete(k); this.purgeExpired();
    this.#m.set(k, { v, at: this.#o.now!() });
    while (this.#m.size > this.#o.maxSize) this.#drop(this.#m.keys().next().value as K, 'capacity');
    return this;
  }
  #live(k: K) { const e = this.#m.get(k); if (!e) return undefined; if (this.#dead(e)) { this.#drop(k, 'expired'); return undefined; } return e; }
  get(k: K): V | undefined { const e = this.#live(k); if (!e) return undefined; this.#m.delete(k); this.#m.set(k, e); return e.v; }
  peek(k: K): V | undefined { return this.#live(k)?.v; }
  has(k: K): boolean { return this.#live(k) !== undefined; }
  delete(k: K): boolean { if (!this.#live(k)) return false; this.#m.delete(k); return true; }
  get size(): number { this.purgeExpired(); return this.#m.size; }
}
