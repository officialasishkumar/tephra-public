// The demo's Assistant tab (docs/UI-DESIGN.md 7.21, the /assistant board's data in the side
// panel): which of the five steps each folded board row belongs to, who took it, how it went, the
// rows at a playhead grouped by minute, and the replay player's words. Pure functions over
// board.js's model (flowModel), no DOM, so Node tests them (tests/test_wall_assist.py). A row is
// never invented: with no steps the panel says so.

import { foldRows, hmsOf, HELPERS, FEED_NAMES, REFUSED, TOOLISH } from "./board.js";

// The five steps' keys in order (five-steps.js holds their words): a step's number is its place.
export const STAGES = ["feeds", "code", "ai", "desk", "record"];
const SKILL_NAME = Object.fromEntries(HELPERS.map((h) => [h.id, h.name]));
const MODEL_ACTORS = new Set(["gemini", "adk", "stub"]);
const ASSISTANT = "TEPHRA Assistant";
// The player plays back at this speed; under reduced motion it moves one step every RM_STEP_MS.
export const PLAY_SPEED = 8;
export const RM_STEP_MS = 2200;

// The step a folded row (board.js foldRows) belongs to, from its kind. A skill's draft reaching the
// Desk ("desk:<skill>") is still the Assistant's step: only a person's decision is step 4, so the
// "A person decides" step never lights for a model's handover.
export function stageOf(row) {
  const kind = String(row?.kind || "");
  if (kind === "feed" || kind === "adsb") return "feeds";
  if (kind === "flight") return "code";
  if (kind === "decided") return "desk";
  if (kind === "note") return MODEL_ACTORS.has(row.items?.[0]?.actor) ? "ai" : "code";
  return "ai";
}

// Who took the step and what kind of actor it is ("public feed", "no AI", "TEPHRA Assistant").
function actorOf(row) {
  const e = row.items?.[0] || {};
  const kind = String(row.kind || "");
  if (kind === "flight") return ["Code checks", "no AI"];
  if (kind === "duty" || kind === "brief" || kind.startsWith("handoff:")) return ["Coordinator", ASSISTANT];
  if (kind.startsWith("skill:") || kind.startsWith("desk:") || kind === "skill-failed") return [SKILL_NAME[e.skill] || ASSISTANT, ASSISTANT];
  if (kind === "feed") return [FEED_NAMES[e.feed] || e.feed || "Public feed", "public feed"];
  if (kind === "adsb") return e.feed === "airline" ? ["Airline positions", "airline feed"] : ["Aircraft positions", "public feed"];
  if (kind === "decided") return ["A person", "the Desk"];
  if (kind === "onreq") return [ASSISTANT, null];
  return MODEL_ACTORS.has(e.actor) ? [ASSISTANT, null] : ["Code", "no AI"];
}

// How the step went: "noresult" for a refused or undone run and a failed or refused skill step,
// "tool" for a tool call on the way, "done" for another skill step, else null (nothing to say).
function resultOf(row) {
  const kind = String(row.kind || "");
  if (kind === "duty") return row.out ? "noresult" : null;
  if (kind === "skill-failed") return "noresult";
  if (!kind.startsWith("skill:") && !kind.startsWith("desk:")) return null;
  if (REFUSED.test(row.text)) return "noresult";
  if (TOOLISH.test(row.text)) return "tool";
  return "done";
}

// One row as the panel shows it. `at` places it on the playhead; `tm` is the record's own time,
// the one shown.
export function rowView(row) {
  const [actor, kind] = actorOf(row);
  return { key: row.key, at: row.at, tm: row.tm ?? row.at, stage: stageOf(row), actor, kind, text: row.text, result: resultOf(row) };
}

// Every row at or before the playhead `t`, newest first.
export function visibleRows(M, t) {
  const events = (M?.events || []).filter((e) => e.at <= t);
  return foldRows(events).map(rowView).reverse();
}

// The rows under their minute ("10:33 UTC"), in the order given.
export function minuteGroups(rows) {
  const out = [];
  for (const r of rows) {
    const minute = `${hmsOf(r.tm).slice(0, 5)} UTC`;
    const last = out[out.length - 1];
    if (last && last.minute === minute) last.rows.push(r);
    else out.push({ minute, rows: [r] });
  }
  return out;
}

// The newest step's time in the window (the live edge of the player).
export const newestAt = (M) => {
  const ev = (M?.events || []).filter((e) => !e.quiet);
  return ev.length ? ev[ev.length - 1].at : NaN;
};

// The steps the player's track draws, oldest first: one tick each, amber for a model's step.
export function trackTicks(M) {
  const ev = (M?.events || []).filter((e) => !e.quiet && e.type !== "note");
  if (!ev.length) return [];
  const t0 = ev[0].at, t1 = ev[ev.length - 1].at, span = Math.max(1, t1 - t0);
  const ai = new Set(["duty", "handoff", "skill", "skill-failed", "desk", "brief", "refused", "undone", "onreq"]);
  return ev.map((e) => ({ at: e.at, frac: (e.at - t0) / span, ai: ai.has(e.type) }));
}

// The player's words for a player state P = { mode: "follow" | "paused" | "playing", t, from, rm }.
// REPLAY always says "Replay" first, and paused says where: never a bare "paused". The player moves
// only this panel's steps: the replay itself, its clock and the map run on, and the words say so.
// LIVE has no player, only one line.
export function playerWords(M, P) {
  if (!M?.replay) return { live: true, lead: "Live", text: "new steps appear as they come" };
  const newest = newestAt(M);
  const at = P.mode === "follow" ? newest : P.t;
  const time = Number.isFinite(at) ? hmsOf(at) : null;
  const pace = P.rm ? "one step at a time" : `at ${PLAY_SPEED}x`;
  if (P.mode === "paused") {
    return { live: false, lead: "Replay", text: `steps paused at ${time || "--:--:--"} (the replay clock runs on)`, time: null, action: "play", button: `Play the steps from ${time || "the start"}`,
      valuetext: `step at replay clock ${time || "--:--:--"}` };
  }
  if (P.mode === "playing") {
    return { live: false, lead: "Replay", text: `playing back from ${hmsOf(P.from)} ${pace}`, time, action: "pause", button: "Pause the steps",
      valuetext: `step at replay clock ${time}` };
  }
  return { live: false, lead: "Replay", text: "TEPHRA's steps on the replayed feeds, at the replay clock", time, action: "pause", button: "Pause the steps",
    valuetext: `step at replay clock ${time || "--:--:--"}, the newest step` };
}

// The panel's state line from the assistant's state words (x-parts aiWords) and the stub flag:
// with no model it says NO MODEL (never removed), else the one state word with its shape and,
// when paused or in trouble, a way to the cause.
export function stateLine(w, { stub = false, kind = "on" } = {}) {
  if (stub || kind === "off") return { strong: "NO MODEL", text: "offline stub: code checks still run", tone: "off", icon: "st-off", why: false };
  if (kind === "paused") return { strong: null, text: w?.suffix || "paused", tone: "caution", icon: "st-caution", why: true };
  if (kind === "trouble") return { strong: null, text: w?.suffix || "gave no result", tone: "caution", icon: "st-caution", why: true };
  return { strong: null, text: w?.suffix || "on", tone: "ok", icon: "st-ok", why: false };
}

// What the screen reader hears for a new step (at most one every 10 s, the panel's rule).
export const sayRow = (r) => `New step: ${r.actor}. ${r.text}`;
