# TtlLruCache — implement in src/cache.ts
`new TtlLruCache<K, V>({ maxSize, ttlMs, now?, onEvict? })`
- `maxSize` must be an integer >= 1, `ttlMs` must be a finite number > 0, else throw `RangeError`.
- `now` is an injectable clock `() => number` (default `Date.now`). An entry written at time t is expired when `now() >= t + ttlMs`.
- `set(key, value)`: inserts or overwrites; makes the key most-recently-used and restarts its TTL. If the cache is over `maxSize`
  afterwards, evict least-recently-used entries until it fits. Returns `this`.
- `get(key)`: returns the value or `undefined`. A hit makes the key most-recently-used but does NOT extend its TTL.
  An expired entry is removed (reported as `expired`) and `undefined` is returned.
- `peek(key)`: like `get` but changes neither recency nor TTL (an expired entry is still removed and reported).
- `has(key)`: true only for a live (unexpired) entry; does not change recency.
- `delete(key)`: removes the key, returns whether a live entry was removed. An expired entry counts as not present (it is removed and reported `expired`).
- `size`: a getter; number of live entries (expired entries are purged first and reported).
- `purgeExpired()`: removes all expired entries, returns how many.
- `onEvict(key, value, reason)` is called with reason `'capacity'` (LRU eviction) or `'expired'`. It is NOT called for explicit `delete` of a live entry
  or for overwriting a key with `set`. If `onEvict` throws, the cache state must still be consistent and the error must propagate to the caller.
- Expired entries never count toward `maxSize`: `set` first purges expired entries (each reported `expired`), then applies the capacity check.
- An entry is removed from the cache BEFORE `onEvict` is called for it.
- `undefined` is a legal value (`has` is true, `get` returns undefined). Iteration order is not part of the API.
