#!/usr/bin/env node
// Independent UI checker for the Wave C1 benchmark (not part of any evaluated skill).
// usage: node check_ui.mjs <file.html> <outdir>   -> writes <outdir>/{390,768,1440}.png and prints JSON
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const [file, outdir] = process.argv.slice(2);
const abs = resolve(file);
mkdirSync(outdir, { recursive: true });
const html = readFileSync(abs, 'utf8');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const REQUIRED = ['Meridian', 'Starter', 'Team', 'Business', '$9', '$29', '$79', '14-day free trial', 'Is my data encrypted?',
  'Can I cancel any time?', 'Do you support Linux?', 'AES-256', 'Subscribe', 'Priority email support', 'SSO and audit log'];

const dir = mkdtempSync(join(tmpdir(), 'c1-chrome-'));
const proc = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${dir}`, '--no-first-run',
  '--force-color-profile=srgb', '--hide-scrollbars', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((res, rej) => {
  let b = ''; const t = setTimeout(() => rej(new Error('chrome start timeout')), 20000);
  proc.stderr.on('data', (d) => { b += d; const m = b.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); res(m[1]); } });
});
const ws = new WebSocket(wsUrl); await new Promise((r) => (ws.onopen = r));
let id = 0; const pend = new Map();
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
const send = (method, params = {}, sessionId) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params, sessionId })); });
const { result: { targetId } } = await send('Target.createTarget', { url: 'about:blank' });
const { result: { sessionId } } = await send('Target.attachToTarget', { targetId, flatten: true });
const ev = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }, sessionId); if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300)); return r.result.result.value; };

const PROBE = `(() => {
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const parse = (s) => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (fg, bg) => { const a = fg[3]; return [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1]; };
  const effBg = (el) => { let stack = []; let n = el; let unknown = false; while (n && n.nodeType === 1) { const cs = getComputedStyle(n); if (cs.backgroundImage && cs.backgroundImage !== 'none') { unknown = true; break; } const c = parse(cs.backgroundColor); if (c && c[3] > 0) { stack.push(c); if (c[3] === 1) break; } n = n.parentElement; } let base = [255, 255, 255, 1]; for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base); return { c: base, unknown }; };
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0'; };
  const out = { w: innerWidth, overflowX: document.documentElement.scrollWidth - innerWidth, contrastFail: 0, contrastUnknown: 0, contrastChecked: 0, worst: 21, small24: 0, interactive: 0 };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  out.invisibleText = 0; const seen = new Set(); let n;
  while ((n = walker.nextNode())) {
    if (!n.textContent.trim()) continue; const el = n.parentElement; if (!el || seen.has(el)) continue; if (!visible(el)) { const cs0 = getComputedStyle(el); if (cs0.display !== 'none' && el.getBoundingClientRect().width > 0 && (cs0.opacity === '0' || cs0.visibility === 'hidden')) out.invisibleText++; continue; } seen.add(el);
    const cs = getComputedStyle(el); const fg = parse(cs.color); if (!fg) continue;
    const { c: bg, unknown } = effBg(el); if (unknown) { out.contrastUnknown++; continue; }
    const ratio = (() => { const f = over(fg, bg); const L1 = lum(f), L2 = lum(bg); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); })();
    const px = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700; const large = px >= 24 || (px >= 18.66 && bold);
    out.contrastChecked++; out.worst = Math.min(out.worst, +ratio.toFixed(2)); if (ratio < (large ? 3 : 4.5)) out.contrastFail++;
  }
  const inter = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[tabindex]:not([tabindex="-1"]),[onclick]')].filter(visible);
  out.interactive = inter.length;
  out.small24 = inter.filter((e) => { const r = e.getBoundingClientRect(); return r.width < 24 || r.height < 24; }).length;
  out.small44 = inter.filter((e) => { const r = e.getBoundingClientRect(); return r.width < 44 || r.height < 44; }).length;
  out.fakeButtons = [...document.querySelectorAll('[onclick]')].filter((e) => !e.matches('a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem]')).length;
  out.imgNoAlt = [...document.images].filter((i) => !i.hasAttribute('alt')).length;
  out.inputNoLabel = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea')].filter((e) => !(e.labels && e.labels.length) && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby')).length;
  out.noFocusStyle = 0; const fo = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[tabindex]:not([tabindex="-1"]),[role=button]')].filter(visible);
  for (const e of fo) { const snap = () => { const s = getComputedStyle(e); return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderColor, s.backgroundColor, s.textDecorationLine, s.color].join('|'); }; const a = snap(); e.focus({ focusVisible: true }); const b = snap(); if (a === b) out.noFocusStyle++; e.blur(); }
  out.lang = !!document.documentElement.getAttribute('lang'); out.title = !!document.title.trim();
  out.viewportMeta = !!document.querySelector('meta[name=viewport]');
  out.h1 = document.querySelectorAll('h1').length;
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) => +h.tagName[1]); out.headingSkips = hs.filter((l, i) => i > 0 && l - hs[i - 1] > 1).length;
  out.landmarks = ['main', 'nav', 'header', 'footer'].filter((t) => document.querySelector(t)).length;
  const txt = document.body.innerText || ''; out.textLen = txt.length;
  out.dom = document.querySelectorAll('*').length;
  out.fontMin = Math.min(...[...document.querySelectorAll('body *')].filter((e) => visible(e) && [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())).map((e) => parseFloat(getComputedStyle(e).fontSize)));
  return out;
})()`;

const res = { file, bytes: html.length, widths: {}, content: {} };
for (const w of [390, 768, 1440]) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false }, sessionId);
  await send('Page.enable', {}, sessionId);
  await send('Page.navigate', { url: 'file://' + abs }, sessionId);
  await new Promise((r) => setTimeout(r, 1500));
  await ev(`(async()=>{const h=document.documentElement.scrollHeight;for(let y=0;y<h;y+=300){window.scrollTo(0,y);await new Promise(r=>setTimeout(r,90));}window.scrollTo(0,h);await new Promise(r=>setTimeout(r,300));window.scrollTo(0,0);await new Promise(r=>setTimeout(r,700));return h})()`);
  const m = await ev(PROBE); res.widths[w] = m;
  const h = await ev('Math.min(document.documentElement.scrollHeight, 6000)');
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width: w, height: h, scale: 1 } }, sessionId);
  writeFileSync(join(outdir, `${w}.png`), Buffer.from(shot.result.data, 'base64'));
  if (w === 1440) { const body = await ev('document.body.textContent + " " + [...document.querySelectorAll("[alt],[aria-label]")].map(e=>e.getAttribute("alt")||e.getAttribute("aria-label")).join(" ")'); res.missing = REQUIRED.filter((s) => !body.toLowerCase().includes(s.toLowerCase())); }
}
res.external = (html.match(/(?:src|href)=["']https?:\/\/(?!www\.w3\.org)[^"']+|@import\s+url\(["']?https?:[^)]+|url\(["']?https?:[^)]+/g) || []).length;
res.reducedMotion = /prefers-reduced-motion/.test(html);
res.hasAnimation = /@keyframes|transition\s*:|animation\s*:/.test(html);
res.inlineHandlers = (html.match(/\sonclick=/g) || []).length;
console.log(JSON.stringify(res));
try { proc.kill('SIGKILL'); } catch {}
rmSync(dir, { recursive: true, force: true });
process.exit(0);
