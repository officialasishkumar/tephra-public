// The demo's welcome dialog (DESIGN 5.2, SPEC-v2 5.2.1): how TEPHRA works in five steps, then the
// honesty lines (what is playing, the fictional airline, decision support only), then Start. It
// opens on a fresh visit unless the link skips it (?intro=0, a screenshot or recording run, or a
// deep link into Details) or the reader ticked "Don't show this again". wall.js opens it, and
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
const LEDE = {
  recorded: "You will watch these five steps run on a real eruption, step by step,",
  reconstructed: "You will watch these five steps run on a real eruption, step by step,",
  synthetic: "You will watch these five steps run on invented demo data, step by step,",
  live: "You will watch these five steps run on today's public feeds,",
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
  if (kind === "synthetic") return ["Invented demo data", day].filter(Boolean).join(" · ");
  return [v, day].filter(Boolean).join(" · ") || null;
}

// Pure: every word the dialog shows for a state. `replay` is null without a state (nothing is said
// about what plays until the server has answered).
export function welcomeWords(state) {
  const kind = replayKind(state);
  const v = kind === "recorded" || kind === "reconstructed" ? volcanoOf(state.replay) : null;
  const day = kind && kind !== "live" ? replayDay(state.replay) : null;
  const lede = LEDE[kind] || "You will watch these five steps run, step by step,";
  return {
    pill: kind === "live" ? "Live" : kind ? "Replay" : null,
    eyebrow: kind ? eyebrowOf(kind, state, v, day) : null,
    lede: `${lede} in the panel on the right.`,
    lede_phone: `${lede} in the panel below.`,
    replay: kind ? replayLine(kind, v, day) : null,
    airline: { lead: "Ring of Fire Air (RFA) is a fictional airline.", text: `Its flight numbers stand in for ${aircraftNoun(state)}.` },
    support: SUPPORT,
  };
}

const honestItem = (iconId, words, cls = null) =>
  el("li", { class: cls }, icon(iconId), el("span", {}, el("b", { text: words.lead }), ` ${words.text}`));

function content(state) {
  const w = welcomeWords(state);
  const live = state?.mode === "LIVE";
  const eyebrow = w.pill && el("p", { class: "welcome__eyebrow" },
    el("span", { class: `welcome__pill${live ? " welcome__pill--live" : ""}` }, icon(live ? "i-live" : "i-replay", "icon icon--16"), w.pill),
    w.eyebrow && el("span", { text: w.eyebrow }));
  const body = el("div", { class: "welcome__body" },
    el("div", { class: "welcome__head" },
      eyebrow,
      el("h2", { id: "welcome-title", text: "How TEPHRA works, in five steps" }),
      el("p", { id: "welcome-lede" },
        el("span", { class: "welcome__wide", text: w.lede }),
        el("span", { class: "welcome__phone", text: w.lede_phone }))),
    stepsList({ size: "lg" }),
    el("ul", { id: "welcome-honest", class: "honest-list", "aria-label": "Before you start" },
      w.replay && honestItem(live ? "i-live" : "i-replay", w.replay, "honest-list__replay"),
      honestItem("i-aircraft", w.airline),
      honestItem("i-hand", w.support)));
  const foot = el("div", { class: "welcome__foot" },
    el("label", { class: "check" }, el("input", { type: "checkbox", id: "welcome-skip" }), "Don't show this again"),
    el("p", { class: "welcome__keys" }, el("kbd", { text: "Enter" }), " or ", el("kbd", { text: "Esc" }), " starts · reopen from How it works"),
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
    // Enter starts from anywhere in the dialog, the "Don't show this again" box included (Space
    // ticks it), as its footer says.
    if (e.key !== "Enter" || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    start(dialog);
  });
  dialog.addEventListener("click", (e) => { if (e.target.closest("#welcome-start")) start(dialog); });
}

export function openWelcome(dialog, state, { opener = null, onClose = () => {} } = {}) {
  if (!dialog || dialog.open) return;
  wire(dialog);
  dialog.replaceChildren(...content(state));
  describeReplay(dialog, state?.mode === "REPLAY" ? replayWords(state.replay).text : "");
  open.set(dialog, { opener, onClose });
  dialog.showModal();
  dialog.querySelector("#welcome-start")?.focus();
}
