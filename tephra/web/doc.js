// The printable page for an SRA draft, a VAR draft or a shift handover: GET /docs/{id}.
// It reads the same JSON the Desk reads (/api/docs/{id}, or /api/desk/handover/{id} for ho_ ids)
// and draws it with the Desk's renderer, on paper. Under a hosted airline (/a/<ICAO>/docs/{id}) it
// reads the airline's own API and carries the airline header above the document's bar.

import { loadSprite } from './desk/dom.js';
import { renderDoc, renderHandover } from './desk/docview.js';
import { TENANT, api, page, rewriteLinks, SHADOW_WORDS } from './base.js';
import { mountTenantNav, onTenantHeader, titleFor } from './tenant-nav.js';

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
  if (TENANT) {
    rewriteLinks(document);
    const bar = document.createElement('header');
    bar.className = 'tn-bar';
    document.querySelector('.docbar').before(bar);
    document.querySelector('.docbar .topnav')?.remove();
    mountTenantNav({ bar, section: 'doc', theme: false });
  }
  await loadSprite();
  const id = documentId();
  if (!/^(DOC-[0-9a-f]{12}|ho_[0-9a-f]{12})$/.test(id)) {
    say('There is no document with that id.', { href: page('/desk'), text: 'Back to the Desk' });
    return;
  }
  const handover = id.startsWith('ho_');
  let res;
  try {
    res = await fetch(handover ? api(`/desk/handover/${encodeURIComponent(id)}`) : api(`/docs/${encodeURIComponent(id)}`), {
      headers: { Accept: 'application/json', 'X-Tephra-Desk': '1' },
      credentials: 'same-origin',
      cache: 'no-store',
    });
  } catch {
    say("Can't reach the TEPHRA server. Check your connection and reload.");
    return;
  }
  if (res.status === 401) {
    say('A handover brief is for signed-in dispatchers.', { href: page('/desk'), text: 'Sign in on the Desk, then reload this page.' });
    return;
  }
  if (!res.ok) {
    say(res.status === 404 ? 'No such document.' : `The server answered HTTP ${res.status}.`, { href: page('/desk'), text: 'Back to the Desk' });
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
  // the footer's fictional-airline clause is the demo's: a document of an airline's own TEPHRA
  // carries no FICTIONAL label (regdocs/common.py) and a brief says fictional_airline false
  const fictional = handover ? doc.fictional_airline !== false : (doc.labels || []).some((l) => /FICTIONAL/.test(l));
  document.getElementById('docfoot-fictional').hidden = !fictional;
  // a draft made while a hosted airline ran in SHADOW says so above the document (D12)
  const stamp = doc.shadow === true ? document.createElement('span') : null;
  if (stamp) {
    stamp.className = 'stamp--shadow';
    stamp.append(document.createElement('i'), SHADOW_WORDS);
  }
  main.replaceChildren(...[stamp, view].filter(Boolean));
  const title = view.querySelector('.dhd__title');
  document.title = `${doc.replay ? 'REPLAY - ' : ''}${title ? title.textContent : 'TEPHRA document'}`;
  if (TENANT) onTenantHeader((h) => { if (h) document.title = titleFor(h, title ? title.textContent : 'Document'); });
  const print = document.getElementById('print');
  print.hidden = false;
  print.addEventListener('click', () => window.print());
  if (title) title.focus({ preventScroll: true });
}

boot();
