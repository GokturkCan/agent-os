// TODO: implement TtlLruCache per SPEC.md
export type EvictReason = 'capacity' | 'expired';
export interface CacheOptions<K, V> {
  maxSize: number;
  ttlMs: number;
  now?: () => number;
  onEvict?: (key: K, value: V, reason: EvictReason) => void;
}
export class TtlLruCache<K, V> {
  constructor(_opts: CacheOptions<K, V>) {
    throw new Error('not implemented');
  }
}
