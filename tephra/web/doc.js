// The printable page for an SRA draft, a VAR draft or a shift handover: GET /docs/{id}.
// It reads the same JSON the Desk reads (/api/docs/{id}, or /api/desk/handover/{id} for ho_ ids)
// and draws it with the Desk's renderer, on paper.

import { loadSprite } from './desk/dom.js';
import { renderDoc, renderHandover } from './desk/docview.js';

const main = document.getElementById('doc-main');
const state = document.getElementById('doc-state');

function say(text, link = null) {
  state.textContent = text;
  if (link) {
    const a = document.createElement('a');
    a.href = link.href;
    a.textContent = link.text;
    state.append(' ', a);
  }
}

function documentId() {
  const q = new URLSearchParams(window.location.search).get('id');
  if (q) return q;
  const parts = window.location.pathname.split('/').filter(Boolean);
  return parts.length ? decodeURIComponent(parts[parts.length - 1]) : '';
}

async function boot() {
  await loadSprite();
  const id = documentId();
  if (!/^(DOC-[0-9a-f]{12}|ho_[0-9a-f]{12})$/.test(id)) {
    say('There is no document with that id.', { href: '/desk', text: 'Back to the Desk' });
    return;
  }
  const handover = id.startsWith('ho_');
  let res;
  try {
    res = await fetch(handover ? `/api/desk/handover/${encodeURIComponent(id)}` : `/api/docs/${encodeURIComponent(id)}`, {
      headers: { Accept: 'application/json', 'X-Tephra-Desk': '1' },
      credentials: 'same-origin',
      cache: 'no-store',
    });
  } catch {
    say("Can't reach the TEPHRA server. Check your connection and reload.");
    return;
  }
  if (res.status === 401) {
    say('A handover brief is for signed-in dispatchers.', { href: '/desk', text: 'Sign in on the Desk, then reload this page.' });
    return;
  }
  if (!res.ok) {
    say(res.status === 404 ? 'No such document.' : `The server answered HTTP ${res.status}.`, { href: '/desk', text: 'Back to the Desk' });
    return;
  }
  let doc;
  try {
    doc = await res.json();
  } catch {
    say('The document could not be read.');
    return;
  }
  const view = handover ? renderHandover(doc) : renderDoc(doc);
  main.replaceChildren(view);
  const title = view.querySelector('.dhd__title');
  document.title = `${doc.replay ? 'REPLAY - ' : ''}${title ? title.textContent : 'TEPHRA document'}`;
  const print = document.getElementById('print');
  print.hidden = false;
  print.addEventListener('click', () => window.print());
  if (title) title.focus({ preventScroll: true });
}

boot();
