// DOM helpers for the Desk. Text always goes in through textContent or text nodes; nothing
// here parses HTML, so feed and model text can never become markup.

const SVG_NS = 'http://www.w3.org/2000/svg';
const SPRITE = '/static/icons.svg';

export const byId = (id) => document.getElementById(id);

// el('p', { class: 'x', text: 'hello', 'aria-label': 'y' }, child, 'text', ...)
export function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = String(value);
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2), value);
    } else node.setAttribute(key, value === true ? '' : String(value));
  }
  append(node, kids);
  return node;
}

export function append(node, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false || kid === '') continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

let spriteInline = false;

// Chrome fetches an external sprite again for each new <use>, so icons drawn while offline
// would vanish. The sprite (our own static file, no scripts or styles) is put in the page once
// and every icon then points inside the document.
export async function loadSprite() {
  try {
    const res = await fetch(SPRITE, { cache: 'force-cache' });
    if (!res.ok) return;
    const doc = new DOMParser().parseFromString(await res.text(), 'image/svg+xml');
    const root = doc.documentElement;
    if (root.localName !== 'svg' || doc.querySelector('parsererror')) return;
    const sprite = document.importNode(root, true);
    sprite.setAttribute('class', 'sprite');
    sprite.setAttribute('aria-hidden', 'true');
    sprite.setAttribute('focusable', 'false');
    document.body.prepend(sprite);
    spriteInline = true;
    for (const use of document.querySelectorAll(`use[href^="${SPRITE}#"]`)) {
      use.setAttribute('href', use.getAttribute('href').slice(SPRITE.length));
    }
  } catch {
    // Icons keep using the external sprite.
  }
}

export function icon(id, cls = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', spriteInline ? `#${id}` : `${SPRITE}#${id}`);
  svg.append(use);
  return svg;
}

// A status shape that is never alone: the word is visible text next to it.
export const status = (shape, word, cls = '') =>
  el('span', { class: `status ${cls}`.trim() }, icon(shape, 'st'), el('span', { text: word }));

let announceTimer = 0;
// One polite live region for the whole page (spec 12): new draft, decision, connection.
export function announce(text) {
  const region = byId('announcer');
  if (!region) return;
  window.clearTimeout(announceTimer);
  region.textContent = '';
  // A fresh text node after a tick makes screen readers read a repeated message again.
  announceTimer = window.setTimeout(() => {
    region.textContent = text;
  }, 60);
}

export const reducedMotion = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const isWide = () => window.matchMedia('(min-width: 1100px)').matches;
