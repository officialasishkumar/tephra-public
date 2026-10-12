// Renders an SRA draft, a VAR draft, a crew report message or a shift handover brief. Shared by the Desk (docs tab) and
// the printable page (doc.html), so it imports nothing from the Desk's state. Blanks stay
// visibly blank: a person fills them, never the page. Model-written boxes carry the model id.
// All text goes in through textContent.

import { el, icon } from './dom.js';
import { dayMonthHhmm, hhmmz } from './format.js';

const ROLE = {
  DISPATCHER: 'Dispatcher',
  SAFETY_MANAGER: 'Safety manager',
  ACCOUNTABLE_EXECUTIVE: 'Accountable executive',
  PILOT_IN_COMMAND: 'Pilot in command',
};
export const roleName = (r) => ROLE[r] || String(r);

const blank = (note) => el('span', { class: 'blank' }, el('span', { class: 'blank__box', 'aria-hidden': 'true' }),
  note === '' ? null : el('span', { class: 'blank__note', text: note || 'TO COMPLETE' }), el('span', { class: 'sr-only', text: ' (blank)' }));

function modelMark(modelId, backend) {
  const stub = backend === 'stub' || modelId === 'stub' || !modelId;
  return el('span', { class: `dmark ${stub ? 'dmark--stub' : 'dmark--ai'}`, title: stub ? 'NO MODEL: written by code templates, not a model' : `Written by ${modelId}, checked by code` },
    icon(stub ? 'i-code' : 'i-sparkle', 'st'), el('span', { text: stub ? 'NO MODEL' : `AI-written · ${modelId}` }));
}

function fieldRow(f, doc) {
  const value = f.value && String(f.value).trim()
    ? el('span', { class: 'fv', text: f.value })
    : blank(f.note || (f.origin === 'human' ? 'PILOT/DISPATCHER TO COMPLETE' : 'TO COMPLETE'));
  const marks = [];
  if (f.origin === 'ai') marks.push(modelMark(doc.model_id, doc.llm_backend));
  if (f.hint) marks.push(el('span', { class: 'fhint', text: f.hint }));
  const row = el('div', { class: `frow ${f.origin === 'human' ? 'frow--human' : ''} ${f.number ? 'frow--item' : ''}`.trim() },
    el('dt', {}, f.number ? el('span', { class: 'fnum', text: String(f.number) }) : null, el('span', { text: f.label })),
    el('dd', {}, value, ...marks,
      f.note && f.value ? el('span', { class: 'fnote', text: f.note }) : null,
      f.source_ids && f.source_ids.length ? el('span', { class: 'fsrc mono', text: f.source_ids.join(' · ') }) : null));
  return row;
}

const fieldList = (fields, doc) => el('dl', { class: 'flist' }, (fields || []).map((f) => fieldRow(f, doc)));

function table(t) {
  return el('div', { class: 'dtable' },
    el('p', { class: 'dtable__t', text: t.title }),
    el('div', { class: 'dtable__wrap' }, el('table', {},
      el('thead', {}, el('tr', {}, t.columns.map((c) => el('th', { scope: 'col', text: c })))),
      el('tbody', {}, t.rows.map((r) => el('tr', {}, r.map((c) => el('td', {}, c === null || c === '' ? blank('') : document.createTextNode(String(c))))))))),
    t.note ? el('p', { class: 'fnote', text: t.note }) : null);
}

const SIGN_NOTE = {
  SRA: 'Signing records who signed and when. It is not a regulator approval.',
  VAR: 'Signing records who signed and when. A VAR is sent only by the crew\'s and the operator\'s own channels, never by TEPHRA.',
  CREW_MESSAGE: 'Signing records who checked the message and when. It goes out only through the operator\'s own channel, never from TEPHRA.',
};

function signatures(doc, onSign) {
  if (doc.status === 'WITHDRAWN') onSign = null;
  return el('section', { class: 'dsec dsec--sig' },
    el('h2', { class: 'dsec__t', text: 'Sign-off' }),
    el('p', { class: 'fnote', text: SIGN_NOTE[doc.kind] || SIGN_NOTE.VAR }),
    el('ul', { class: 'sigs' }, doc.signatures.map((s) => el('li', { class: `sig ${s.signed_at ? 'is-signed' : ''}`.trim() },
      el('span', { class: 'sig__role', text: s.label || roleName(s.role) }),
      s.signed_at
        ? el('span', { class: 'sig__who' }, icon('i-approved', 'st'), el('span', { text: `${s.signed_name} · ${dayMonthHhmm(s.signed_at)}` }), s.recorded_by ? el('span', { class: 'fsrc', text: `recorded by ${s.recorded_by.replace(/^desk:/, '')}` }) : null)
        : el('span', { class: 'sig__who sig__who--open' }, blank('Not signed')),
      !s.signed_at && onSign ? el('button', { type: 'button', class: 'btn sig__btn', onclick: (e) => onSign(s, e.currentTarget.closest('li'), e.currentTarget) }, icon('i-pen-line'), el('span', { text: 'Sign…' })) : null))));
}

function docHead(doc) {
  const title = doc.kind === 'SRA' ? `Safety risk assessment: ${doc.region_name}` : doc.kind === 'CREW_MESSAGE' ? doc.title : `Volcanic activity report: ${doc.proxy_flight} / ${doc.volcano_name}`;
  const status = doc.status === 'SIGNED' ? ['dchip--ok', 'All lines signed'] : doc.status === 'WITHDRAWN' ? ['dchip--warn', 'WITHDRAWN: not to be sent'] : ['', 'DRAFT'];
  return el('header', { class: 'dhd' },
    el('p', { class: 'dhd__banner', role: 'note', text: doc.header }),
    el('h1', { class: 'dhd__title', id: 'doc-title', tabindex: '-1', text: title }),
    el('p', { class: 'dhd__chips' },
      el('span', { class: `dchip ${status[0]}`.trim(), text: status[1] }),
      ...(doc.labels || []).filter((l) => !/^NO MODEL$/i.test(l)).map((l) => el('span', { class: `dchip ${/REPLAY/i.test(l) ? 'dchip--replay' : ''}`.trim(), text: l })),
      doc.kind === 'SRA' ? modelMark(doc.model_id, doc.llm_backend) : null),
    el('p', { class: 'dhd__meta mono', text: `${doc.id} · v${doc.version} · drafted ${dayMonthHhmm(doc.created_at)}${doc.kind === 'SRA' ? ` · policy ${doc.policy_id} v${doc.policy_version}` : ''}` }));
}

function renderSra(doc, opts) {
  const root = el('article', { class: 'docv', 'aria-labelledby': 'doc-title' }, docHead(doc));
  for (const s of doc.sections) {
    root.append(el('section', { class: 'dsec', 'aria-labelledby': `sec-${s.key}` },
      el('h2', { class: 'dsec__t', id: `sec-${s.key}` }, el('span', { class: 'dsec__n', text: String(s.number) }), el('span', { text: s.title })),
      s.reference ? el('p', { class: 'dsec__ref', text: s.reference }) : null,
      s.fields && s.fields.length ? fieldList(s.fields, doc) : null,
      ...(s.tables || []).map(table)));
  }
  if (doc.source_ids && doc.source_ids.length) {
    root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Sources cited' }), el('p', { class: 'fsrc mono', text: doc.source_ids.join(' · ') })));
  }
  root.append(signatures(doc, opts.onSign));
  return root;
}

function renderVar(doc, opts) {
  const root = el('article', { class: 'docv', 'aria-labelledby': 'doc-title' }, docHead(doc));
  root.append(el('p', { class: 'fnote', text: 'The aircraft is an ADS-B proxy flight of the fictional airline, never a real operator\'s flight.' }));
  root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Report header' }), fieldList(doc.header_fields, doc)));
  const group = (name, title) => {
    const items = doc.items.filter((i) => i.group === name).sort((a, b) => a.number - b.number);
    return el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: title }), fieldList(items, doc));
  };
  root.append(group('in_flight', 'In-flight report (items 1 to 8)'), group('post_flight', 'Post-flight report (items 9 to 16)'));
  root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Lines to send' }),
    fieldList([doc.airep_special, doc.ars_line, doc.non_encounter].filter(Boolean), doc)));
  if (doc.context && doc.context.length) root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Context from TEPHRA' }), fieldList(doc.context, doc)));
  if (doc.followups && doc.followups.length) {
    root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Follow-ups' }), el('ul', { class: 'plist' }, doc.followups.map((f) => el('li', { text: f })))));
  }
  root.append(signatures(doc, opts.onSign));
  return root;
}

// The message to the weather office and the VAAC from a crew report: who it is for, the subject
// and the code-written text, then what each line rests on.
function renderCrewMessage(doc, opts) {
  const root = el('article', { class: 'docv', 'aria-labelledby': 'doc-title' }, docHead(doc));
  if (doc.withdrawn_note) root.append(el('p', { class: 'dmsg__withdrawn', role: 'note', text: `${doc.withdrawn_note}. This message is not to be sent.` }));
  root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Message' }),
    fieldList([...doc.to, doc.subject], doc),
    el('pre', { class: 'dmsg__body', text: doc.body })));
  root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'What it rests on' }), fieldList(doc.facts, doc)));
  if (doc.followups && doc.followups.length) {
    root.append(el('section', { class: 'dsec' }, el('h2', { class: 'dsec__t', text: 'Before it goes' }), el('ul', { class: 'plist' }, doc.followups.map((f) => el('li', { text: f })))));
  }
  root.append(signatures(doc, opts.onSign));
  return root;
}

export function renderDoc(doc, opts = {}) {
  if (doc.kind === 'CREW_MESSAGE') return renderCrewMessage(doc, opts);
  return doc.kind === 'VAR' ? renderVar(doc, opts) : renderSra(doc, opts);
}

// --- shift handover (WEST + I-PASS) -----------------------------------------------------------

const SEVERITY = {
  calm: ['st-ok', 'Calm'],
  watch: ['st-caution', 'Watch'],
  active: ['st-caution', 'Active'],
  critical: ['st-serious', 'Critical'],
};

function srcIds(ids) {
  return ids && ids.length ? el('span', { class: 'fsrc mono', text: ids.join(' · ') }) : null;
}

function hsec(letter, title, ...kids) {
  return el('section', { class: 'dsec hsec' }, el('h2', { class: 'dsec__t' }, el('span', { class: 'dsec__n', text: letter }), el('span', { text: title })), ...kids);
}

export function renderHandover(b, { onAck = null, ackBusy = false } = {}) {
  const [shape, word] = SEVERITY[b.severity] || SEVERITY.watch;
  const root = el('article', { class: 'docv hov', 'aria-labelledby': 'doc-title' });
  root.append(el('header', { class: 'dhd' },
    el('p', { class: 'dhd__banner', role: 'note', text: 'DRAFT HANDOVER BRIEF - DECISION SUPPORT ONLY - FICTIONAL AIRLINE' }),
    el('h1', { class: 'dhd__title', id: 'doc-title', tabindex: '-1', text: 'Shift handover' }),
    el('p', { class: 'dhd__chips' },
      el('span', { class: `sev sev--${b.severity}` }, icon(shape, 'st'), el('span', { text: `Illness severity: ${word}` })),
      b.replay ? el('span', { class: 'dchip dchip--replay', text: 'REPLAY' }) : null,
      modelMark(b.model_id, b.llm_backend)),
    el('p', { class: 'dhd__meta mono', text: `${b.id} · shift ${dayMonthHhmm(b.shift_from)} to ${dayMonthHhmm(b.shift_to)} · ${b.outgoing} → ${b.incoming}` }),
    el('p', { class: 'fnote', text: 'Severity, traffic, decisions and every number are gathered by code. The model wrote only the situation and the contingencies.' })));

  root.append(hsec('S', 'Situation', el('p', { class: 'hsit', text: b.situation.text }), srcIds(b.situation.source_ids), modelMark(b.model_id, b.llm_backend)));

  const w = b.weather_ash;
  root.append(hsec('W', 'Weather and ash',
    w.official_areas.length ? el('ul', { class: 'hlist' }, w.official_areas.map((a) => el('li', {},
      el('span', { class: 'hl__k', text: a.label }),
      el('span', { text: ` ${a.base_ft <= 0 ? 'SFC' : `FL${String(Math.round(a.base_ft / 100)).padStart(3, '0')}`} to FL${String(Math.round(a.top_ft / 100)).padStart(3, '0')} · ${hhmmz(a.valid_from)} to ${hhmmz(a.valid_to)}` }),
      el('span', { class: 'fsrc mono', text: a.source_id })))) : el('p', { class: 'note', text: 'No official ash area is valid in the shift.' }),
    w.latest_vaa_utc ? el('p', { class: 'fnote', text: `Latest advisory ${dayMonthHhmm(w.latest_vaa_utc)}.` }) : null,
    w.disagreements.length ? el('div', {}, el('p', { class: 'caps', text: 'Where products disagree' }), el('ul', { class: 'plist' }, w.disagreements.map((d) => el('li', {}, el('span', { text: d.text }), srcIds(d.source_ids))))) : null));

  const e = b.equipment_data;
  root.append(hsec('E', 'Equipment and data',
    e.feeds_stale.length ? el('p', {}, el('span', { class: 'dchip dchip--warn' }, icon('st-stale', 'st'), el('span', { text: `Stale: ${e.feeds_stale.join(', ')}` }))) : el('p', { class: 'note', text: 'All feeds fresh.' }),
    e.data_gaps.length ? el('ul', { class: 'plist' }, e.data_gaps.map((g) => el('li', { text: g }))) : null));

  root.append(hsec('T', 'Traffic',
    b.traffic.length ? el('div', { class: 'dtable__wrap' }, el('table', { class: 'htable' },
      el('thead', {}, el('tr', {}, ['Flight', 'Plan', 'Status', 'Why'].map((c) => el('th', { scope: 'col', text: c })))),
      el('tbody', {}, b.traffic.map((r) => el('tr', {}, el('th', { scope: 'row', class: 'mono', text: r.flight }), el('td', { text: r.plan }), el('td', { text: r.status }), el('td', { text: r.reason }))))))
      : el('p', { class: 'note', text: 'No exposed flights in the shift.' })));

  root.append(hsec('A', 'Actions still open',
    b.actions_open.length ? el('ul', { class: 'hlist' }, b.actions_open.map((a) => el('li', {}, el('span', { class: 'hl__k', text: a.owner }), el('span', { text: ` ${a.action}${a.due_utc ? ` · by ${hhmmz(a.due_utc)}` : ''}` }), srcIds(a.source_ids)))) : el('p', { class: 'note', text: 'None.' }),
    b.handed_over_open.length ? el('p', { class: 'fnote', text: `Handed over open (not decided): ${b.handed_over_open.join(', ')}` }) : null));

  root.append(hsec('C', 'Contingencies (if / then)',
    b.contingencies.length ? el('ul', { class: 'hcont' }, b.contingencies.map((c) => el('li', {}, el('span', {}, el('strong', { text: 'If ' }), c.condition), el('span', {}, el('strong', { text: 'then ' }), c.then), srcIds(c.source_ids)))) : el('p', { class: 'note', text: 'None written.' }),
    b.contingencies.length ? modelMark(b.model_id, b.llm_backend) : null));

  root.append(hsec('D', 'Decisions made',
    b.decisions_made.length ? el('ul', { class: 'hlist' }, b.decisions_made.map((d) => el('li', {}, el('span', { class: 'hl__k', text: `${hhmmz(d.utc)} ${d.by}` }), el('span', { text: ` ${d.what}` }), srcIds(d.source_ids)))) : el('p', { class: 'note', text: 'No decision in the shift.' })));

  const ack = b.receiver_ack || {};
  const done = Boolean(ack.read_back_by);
  const synth = hsec('R', 'Synthesis by the receiver (read-back)');
  if (done) {
    synth.append(el('p', { class: 'hack' }, icon('i-approved', 'st'), el('strong', { text: `Read back by ${ack.read_back_by}` }), el('span', { text: ` at ${dayMonthHhmm(ack.utc)}` })));
    if (ack.open_drafts && ack.open_drafts.length) synth.append(el('p', { class: 'fnote', text: `Handed over open: ${ack.open_drafts.join(', ')}` }));
  } else {
    synth.append(el('p', { class: 'note', text: 'The incoming dispatcher reads the brief back. Open drafts are recorded as handed over open, not decided.' }));
    if (onAck) {
      synth.append(el('button', { type: 'button', class: 'btn btn--neutral', 'data-ack': b.id, disabled: ackBusy, onclick: onAck }, icon('i-check'), el('span', { text: 'Read back' })));
    } else synth.append(blank('Not read back'));
  }
  root.append(synth);
  return root;
}
