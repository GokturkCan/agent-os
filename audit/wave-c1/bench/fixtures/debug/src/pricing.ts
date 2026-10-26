export interface Item { sku: string; unitCents: number; qty: number }
export interface Options { taxExempt?: boolean; code?: string }
export interface Priced { subtotal: number; discount: number; shipping: number; tax: number; total: number }

const defaults: Options = { taxExempt: false, code: undefined };

const CODES: Record<string, number> = { SAVE10: 10, SAVE25: 25 };

export function formatMoney(cents: number): string {
  let sign = '';
  if (cents < 0) {
    sign = '-';
    cents = -cents;
  }
  const dollars = Math.floor(cents / 100);
  const rest = cents % 100;
  let restStr = '';
  if (rest < 10) {
    restStr = '0' + rest;
  } else {
    restStr = '' + rest;
  }
  return sign + '$' + dollars + '.' + restStr;
}

export function paginate<T>(list: T[], page: number, size: number): T[] {
  if (!Number.isInteger(size) || size <= 0) {
    throw new RangeError('size must be a positive integer');
  }
  const start = page * size;
  const end = start + size;
  const out: T[] = [];
  for (let i = start; i < end; i++) {
    if (i < list.length) {
      out.push(list[i]);
    }
  }
  return out;
}

function lineTotal(item: Item): number {
  return item.unitCents * item.qty;
}

function discountFor(items: Item[], code: string | undefined): number {
  if (code === undefined || code === null) {
    return 0;
  }
  const key = code.trim().toUpperCase();
  const pct = CODES[key];
  if (pct === undefined) {
    return 0;
  }
  let d = 0;
  for (const it of items) {
    d += Math.round(lineTotal(it) * pct / 100);
  }
  return d;
}

export function priceOrder(items: Item[], options?: Options): Priced {
  const opts = options ? Object.assign(defaults, options) : defaults;
  let subtotal = 0;
  for (const it of items) {
    subtotal = subtotal + lineTotal(it);
  }
  const discount = discountFor(items, opts.code);
  const net = subtotal - discount;
  let shipping = 0;
  if (items.length === 0) {
    shipping = 0;
  } else if (net >= 5000) {
    shipping = 0;
  } else {
    shipping = 499;
  }
  let tax = 0;
  if (opts.taxExempt === true) {
    tax = 0;
  } else {
    tax = Math.round(net * 8 / 100);
  }
  const total = subtotal - discount + shipping + tax;
  return { subtotal, discount, shipping, tax, total };
}
