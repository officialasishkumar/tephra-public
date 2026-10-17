// REPLAY on the Desk, said once (owner's lead, 17 Oct, item K3): one header chip "REPLAY 10:32Z" on
// the replay clock, whose (i) says what a replay is and that the airline is fictional. Decide and the
// review had no visible REPLAY label before (only the page title). Hidden while live: the Desk then
// shows the feeds as they arrive, and the live clock is the wall clock.

import { byId, el } from './dom.js';
import { activeNow, hhmmz } from './format.js';
import { app } from './state.js';
import { infoButton } from '../wall/info.js';
import { fitHead } from './budget.js';
import { replayWords } from '../wall/x-parts.js';

let timer = 0;

// "Feeds rebuilt from archives, from 05 Sep 2026. The clock shows that day, not now. Ring of Fire
// Air (RFA) is a fictional airline."
export function replayWhy(state) {
  const r = replayWords(state.replay);
  const what = r.text.replace(/^Replay · /, '');
  const airline = state.airline && state.airline.fictional === false
    ? ''
    : ` ${state.airline && state.airline.name ? `${state.airline.name} (${state.airline.code})` : 'Ring of Fire Air (RFA)'} is a fictional airline.`;
  return `${what.charAt(0).toUpperCase()}${what.slice(1)}. The clock shows that day, not now.${airline}`;
}

function tick() {
  const clock = byId('mode-clock');
  if (clock) clock.textContent = hhmmz(activeNow());
}

export function drawModeChip() {
  const host = byId('mode-chip');
  if (!host || !app.state) return;
  const replay = app.state.mode === 'REPLAY';
  host.hidden = !replay;
  window.clearInterval(timer);
  if (!replay) {
    host.replaceChildren();
    delete host.dataset.key;
    fitHead();
    return;
  }
  const why = replayWhy(app.state);
  if (host.dataset.key !== why) {
    host.dataset.key = why;
    const old = host.querySelector('.info');
    if (old) old.close();
    // the chip is its own (i): one control, so it fits a phone's header
    host.replaceChildren(infoButton({
      topic: 'replay', text: why, cls: 'dmode__wrap',
      face: [el('span', { class: 'dmode__word', text: 'REPLAY' }), el('span', { id: 'mode-clock', class: 'dmode__clock mono' }),
        el('span', { class: 'sr-only', text: ' (replay clock)' })],
    }));
  }
  tick();
  timer = window.setInterval(tick, 5000);
  fitHead();
}
