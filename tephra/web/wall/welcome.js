// The demo's welcome dialog (DESIGN 5.2, SPEC-v2 5.2.1), a card read at a glance: what plays, one
// title, the five steps by name, one quiet line of honesty facts (where the feeds come from, the
// fictional airline, a person approves) and Start. The full sentences are its screen-reader
// description; the status line and About say them on the page. It
// opens on a fresh visit unless the link skips it (?intro=0, a screenshot or recording run, or a
// deep link into Details) or the reader ticked "Don't show again". wall.js opens it, and
// reopens it from How it works and the W key. Words come from the state, through textContent.

import { el, icon } from "./util.js";
import { describeReplay, replayWords, aircraftNoun } from "./x-parts.js";
import { stepsList } from "../five-steps.js";
import { volcanoOf, replayDay, replayKind } from "../replay-words.js";

export const WELCOME_KEY = "tephra.demo.welcome";

export function welcomeSkipped() {
  try {
    return localStorage.getItem(WELCOME_KEY) === "skip";
  } catch {
    return false;
  }
}

export function shouldOpenWelcome(params, hash = "") {
  const deepLink = /^#(details-[a-z]+|track-record|ai-at-work)$/.test(hash);
  return !deepLink && params.get("intro") !== "0" && params.get("shots") !== "1" && params.get("present") !== "1" && !welcomeSkipped();
}

const SUPPORT = { lead: "Decision support only.", text: "A person approves every advisory, and nothing is sent to an aircraft." };
// the short words on the card's one honesty line, by what plays
const SOURCE = {
  recorded: "Recorded feeds",
  reconstructed: "Rebuilt from archives",
  synthetic: "Invented demo data",
  live: "Feeds as they arrive",
};
const KEEP_CLOCK = "The replay clock shows that day's time, not now.";

function replayLine(kind, v, day) {
  const of = v ? [`the ${v} eruption`, day && `of ${day}`].filter(Boolean).join(" ") : day;
  if (kind === "live") return { lead: "Live.", text: "Public feeds as they arrive. The clock shows the time now (UTC)." };
  if (kind === "synthetic") return { lead: "Replay.", text: "Invented demo data, played back. The replay clock shows the demo's time, not now." };
  if (kind === "reconstructed") return { lead: "Replay.", text: `Public feeds${of ? ` from ${of}` : ""}, rebuilt from archives and played back. ${KEEP_CLOCK}` };
  return { lead: "Replay.", text: `Recorded feeds${of ? ` from ${of}` : ""}. ${KEEP_CLOCK}` };
}

function eyebrowOf(kind, state, v, day) {
  if (kind === "live") return state.region?.name || null;
  return [v, day].filter(Boolean).join(" · ") || null;
}

function titleOf(kind, v) {
  if (kind === "live") return "Watch TEPHRA work today's feeds";
  if (kind === "synthetic") return "Watch TEPHRA work a demo eruption";
  if (kind) return v ? "Watch TEPHRA work a real eruption" : "Watch TEPHRA work a recorded day";
  return "Watch TEPHRA work";
}

// Pure: every word the dialog shows for a state. `replay` is null without a state (nothing is said
// about what plays until the server has answered).
export function welcomeWords(state) {
  const kind = replayKind(state);
  // an airline's own TEPHRA (state.airline.fictional false) names its own airline
  const own = state?.airline?.fictional === false ? state.airline : null;
  const v = kind === "recorded" || kind === "reconstructed" ? volcanoOf(state.replay) : null;
  const day = kind && kind !== "live" ? replayDay(state.replay) : null;
  return {
    pill: kind === "live" ? "Live" : kind ? "Replay" : null,
    eyebrow: kind ? eyebrowOf(kind, state, v, day) : null,
    title: titleOf(kind, v),
    // the card's one honesty line: a few words each, the full sentences below for a screen reader
    facts: [
      kind && { icon: kind === "live" ? "i-live" : "i-replay", text: SOURCE[kind], replay: true },
      own ? { icon: "i-aircraft", text: `Only ${own.code} flights are checked` } : { icon: "i-aircraft", text: "RFA is a fictional airline" },
      { icon: "i-hand", text: "A person approves every advisory" },
    ].filter(Boolean),
    replay: kind ? replayLine(kind, v, day) : null,
    airline: own
      ? { lead: `This TEPHRA checks only ${own.name}'s own flights (${own.code}).`, text: "Each is named by its callsign, schedule or registration." }
      : { lead: "Ring of Fire Air (RFA) is a fictional airline.", text: `Its flight numbers stand in for ${aircraftNoun(state)}.` },
    support: SUPPORT,
  };
}

const sentence = (words) => words && `${words.lead} ${words.text}`;

export function welcomeContent(state) {
  const w = welcomeWords(state);
  const live = state?.mode === "LIVE";
  const eyebrow = w.pill && el("p", { class: "welcome__eyebrow" },
    el("span", { class: `welcome__pill${live ? " welcome__pill--live" : ""}` }, icon(live ? "i-live" : "i-replay", "icon icon--16"), w.pill),
    w.eyebrow && el("span", { text: w.eyebrow }));
  const body = el("div", { class: "welcome__body" },
    el("div", { class: "welcome__head" },
      eyebrow,
      el("h2", { id: "welcome-title", text: w.title })),
    stepsList({ size: "lg", lines: false }),
    el("p", { class: "welcome__facts", "aria-hidden": "true" },
      w.facts.map((f) => el("span", { class: f.replay ? "welcome__fact welcome__fact--replay" : "welcome__fact" }, icon(f.icon, "icon icon--16"), f.text))),
    el("p", { id: "welcome-more", class: "sr-only", text: [w.replay, w.airline, w.support].map(sentence).filter(Boolean).join(" ") }));
  const foot = el("div", { class: "welcome__foot" },
    el("label", { class: "check" }, el("input", { type: "checkbox", id: "welcome-skip" }), "Don't show again"),
    el("button", { type: "button", id: "welcome-start", class: "btn btn--primary", autofocus: true }, "Start the demo", icon("i-arrow-right")));
  return [body, foot];
}

const open = new WeakMap(); // dialog -> { opener, onClose } of the current opening

function start(dialog) {
  const now = open.get(dialog);
  if (!now) return;
  open.delete(dialog);
  if (dialog.querySelector("#welcome-skip")?.checked) {
    try {
      localStorage.setItem(WELCOME_KEY, "skip");
    } catch {
      /* storage blocked: the dialog opens again next time */
    }
  }
  if (dialog.open) dialog.close();
  const back = now.opener?.isConnected ? now.opener : document.getElementById("map-pane");
  back?.focus({ preventScroll: true });
  now.onClose();
}

function wire(dialog) {
  if (dialog.dataset.wired) return;
  dialog.dataset.wired = "1";
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); start(dialog); });
  dialog.addEventListener("keydown", (e) => {
    // Enter starts from anywhere in the dialog, the "Don't show again" box included (Space ticks
    // it); Esc starts too (the cancel event). How it works and the W key reopen it.
    if (e.key !== "Enter" || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    start(dialog);
  });
  dialog.addEventListener("click", (e) => { if (e.target.closest("#welcome-start")) start(dialog); });
}

export function openWelcome(dialog, state, { opener = null, onClose = () => {} } = {}) {
  if (!dialog || dialog.open) return;
  wire(dialog);
  dialog.replaceChildren(...welcomeContent(state));
  describeReplay(dialog, state?.mode === "REPLAY" ? replayWords(state.replay).text : "");
  open.set(dialog, { opener, onClose });
  dialog.showModal();
  dialog.querySelector("#welcome-start")?.focus();
}
