// The demo's Assistant tab (docs/UI-DESIGN.md 7.21, the /assistant board's data in the side
// panel): which of the five steps each folded board row belongs to, who took it, how it went, the
// rows at a playhead grouped by minute, the replay player's words and the catch-up a visitor sees
// on arrival (lastChain: TEPHRA's last chain of recorded steps, from a feed read to You decide).
// Pure functions over board.js's model (flowModel), no DOM, so Node tests them
// (tests/test_wall_assist.py). A row or a step is never invented: with no steps the panel says so.

import { foldRows, hmsOf, HELPERS, FEED_NAMES, REFUSED, TOOLISH } from "./board.js";
import { templateText } from "./x-parts.js";

// The five steps' keys in order (five-steps.js holds their words): a step's number is its place.
export const STAGES = ["feeds", "code", "ai", "desk", "record"];
const SKILL_NAME = Object.fromEntries(HELPERS.map((h) => [h.id, h.name]));
const MODEL_ACTORS = new Set(["gemini", "adk", "stub"]);
const ASSISTANT = "TEPHRA Assistant";
// The player plays back at this speed; under reduced motion it moves one step every RM_STEP_MS.
export const PLAY_SPEED = 8;
export const RM_STEP_MS = 2200;
// The catch-up plays its chain in about this long, each step at least CATCHUP_MIN_MS and at most
// CATCHUP_MAX_MS (under reduced motion every step takes RM_STEP_MS).
export const CATCHUP_MS = 16000;
const CATCHUP_MIN_MS = 1600;
const CATCHUP_MAX_MS = 3200;

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

// Who took the step, by name only: no kind tag under it (the name says it).
function actorOf(row) {
  const e = row.items?.[0] || {};
  const kind = String(row.kind || "");
  if (kind === "flight") return "Code checks";
  if (kind === "duty" || kind === "brief" || kind.startsWith("handoff:")) return "Coordinator";
  if (kind.startsWith("skill:") || kind.startsWith("desk:") || kind === "skill-failed") return SKILL_NAME[e.skill] || ASSISTANT;
  if (kind === "feed") return FEED_NAMES[e.feed] || e.feed || "Public feed";
  if (kind === "adsb") return e.feed === "airline" ? "Airline positions" : "Aircraft positions";
  if (kind === "decided") return "A person";
  if (kind === "onreq") return ASSISTANT;
  return MODEL_ACTORS.has(e.actor) ? ASSISTANT : "Code";
}

// How the step went: "noresult" for a refused or undone run and a failed or refused skill step,
// "tool" for a tool call on the way, "done" for another skill step, else null (nothing to say).
function resultOf(row) {
  const kind = String(row.kind || "");
  if (kind === "duty") return null;
  if (kind === "skill-failed") return "noresult";
  if (!kind.startsWith("skill:") && !kind.startsWith("desk:")) return null;
  if (REFUSED.test(row.text)) return "noresult";
  if (TOOLISH.test(row.text)) return "tool";
  return "done";
}

// One row as the panel shows it. `at` places it on the playhead; `tm` is the record's own time,
// the one shown.
// A step a code template wrote (the offline stub) drops its "(code only)" words and the assistant's
// name for the small "{ }" mark (`code`): the AI-off state is said once, in the tab bar.
export function rowView(row) {
  const actor = actorOf(row);
  const t = templateText(row.text);
  const code = t.code || (row.items || []).some((e) => e.actor === "stub");
  // the row names its actor once: "Aircraft positions · public feed / Read (adsb.lol)", not
  // "... / Aircraft positions read (adsb.lol)" (UX verify, 17 Oct)
  const text = actor && t.text.startsWith(`${actor} `) && t.text.length > actor.length + 1
    ? `${t.text.charAt(actor.length + 1).toUpperCase()}${t.text.slice(actor.length + 2)}` : t.text;
  return { key: row.key, at: row.at, tm: row.tm ?? row.at, stage: stageOf(row), actor, text, code, result: resultOf(row) };
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

// The player's words for a player state P = { mode: "waiting" | "catchup" | "follow" | "paused" | "playing",
// t, from, rm }, shown as "Replay · <text>". REPLAY always says "Replay" first, and paused says
// where: never a bare "paused". The player moves only this panel's steps: the replay itself, its
// clock and the map run on, and the words say so. LIVE has no player, only one line.
export function playerWords(M, P) {
  // LIVE is said once, by the header's pill: the line says only how the steps come
  if (!M?.replay) return { live: true, lead: "", text: "new steps appear as they come" };
  const newest = newestAt(M);
  const at = P.mode === "follow" ? newest : P.t;
  const time = Number.isFinite(at) ? hmsOf(at) : null;
  const pace = P.rm ? "one step at a time" : `at ${PLAY_SPEED}x`;
  if (P.mode === "waiting") {
    return { live: false, lead: "Replay", text: "about to catch up", time: null, action: "pause", button: "Pause the steps",
      valuetext: "the newest step, about to catch up" };
  }
  if (P.mode === "catchup") {
    return { live: false, lead: "Replay", text: "catching up", time, action: "pause", button: "Pause the steps",
      valuetext: `step at replay clock ${time || "--:--:--"}, catching up` };
  }
  if (P.mode === "paused") {
    return { live: false, lead: "Replay", text: `paused at ${time || "--:--:--"}, replay clock runs on`, time: null, action: "play", button: `Play the steps from ${time || "the start"}`,
      valuetext: `step at replay clock ${time || "--:--:--"}` };
  }
  if (P.mode === "playing") {
    return { live: false, lead: "Replay", text: `playing back from ${hmsOf(P.from)} ${pace}`, time, action: "pause", button: "Pause the steps",
      valuetext: `step at replay clock ${time}` };
  }
  return { live: false, lead: "Replay", text: "following the clock", time, action: "pause", button: "Pause the steps",
    valuetext: `step at replay clock ${time || "--:--:--"}, the newest step` };
}

// What the screen reader hears for a new step (at most one every 10 s, the panel's rule), and for
// each step the catch-up plays: old recorded steps, so they are said as the replay's, never as new.
export const sayRow = (r) => `New step: ${r.actor}. ${r.text}`;
export const sayBeat = (b) => `Replay, catching up: ${b.say || b.text}.`;

// ---------------------------------------------------------------- the catch-up (on arrival)
// TEPHRA's last chain of kept steps, in the pipeline's order: the feed reads the newest Coordinator
// run followed, the code checks of that tick, the Coordinator, each skill it reached, then what came
// to a person (drafts at the Desk, or must-do work when the run did not run). Each beat is real
// events (their ids); nothing is added. A chain with a part missing from the steps this page holds
// is played as it is, and `missing` says which part.
const COORD = new Set(["duty", "refused", "undone", "handoff", "brief"]);
const WORK = new Set(["skill", "skill-failed", "desk"]);
const RUN_GAP_MS = 30000; // the steps of one run are this close together
const BEFORE_MS = 120000; // the reads of one tick come at most this long apart
const MAX_RUNS = 30; // the catch-up looks this many runs back for a full chain
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const readKey = (e) => (e.type === "adsb" ? e.feed || "adsb" : e.feed);

function readsBefore(ev, t) {
  const held = ev.filter((e) => (e.type === "feed" || e.type === "adsb") && e.at <= t);
  if (!held.length) return [];
  const newest = held[held.length - 1].at;
  const per = new Map();
  for (const e of held) if (e.at >= newest - BEFORE_MS) per.set(readKey(e), e);
  return [...per.values()].sort((a, b) => a.at - b.at);
}

function beat(kind, node, evs, text, extra = {}) {
  return { kind, node, ids: evs.map((e) => e.id), from: evs[0].at, at: evs[evs.length - 1].at, n: evs.length, text, ...extra };
}

// The chain of the run whose newest Coordinator step is ev[li] (li < 0: no run, the newest code
// checks and their reads). `run` is the run's own steps, oldest first.
function runAt(ev, li) {
  const inRun = (e) => COORD.has(e.type) || WORK.has(e.type);
  const run = [ev[li]];
  for (let i = li - 1, prev = ev[li].at; i >= 0; i--) {
    if (!inRun(ev[i])) continue;
    if (prev - ev[i].at > RUN_GAP_MS) break;
    run.unshift(ev[i]); prev = ev[i].at;
  }
  for (let i = li + 1, last = ev[li].at; i < ev.length; i++) {
    if (!inRun(ev[i])) continue;
    if (ev[i].at - last > RUN_GAP_MS) break;
    run.push(ev[i]); last = ev[i].at;
  }
  return run;
}

function chainOf(ev, run) {
  const beats = [];
  const start = run.length ? run[0].at : Infinity;
  const end = run.length ? run[run.length - 1].at : Infinity;
  // the code checks of the run's tick, or with no run the newest tick's
  let flights = ev.filter((e) => e.type === "flight" && e.at <= end && e.at >= start - RUN_GAP_MS);
  if (!run.length) {
    const all = ev.filter((e) => e.type === "flight");
    const newest = all.length ? all[all.length - 1].at : NaN;
    flights = all.filter((e) => e.at >= newest - RUN_GAP_MS);
  }
  const readsTo = flights.length ? flights[0].at : Number.isFinite(start) ? start : Infinity;
  const reads = readsBefore(ev, readsTo);
  if (reads.length) beats.push(beat("feeds", "code", reads, `Feed reads: ${[...new Set(reads.map((e) => FEED_NAMES[readKey(e)] || readKey(e)))].join(", ")}`, { feeds: reads.map(readKey) }));
  if (flights.length) {
    const names = [...new Set(flights.map((e) => e.flight))];
    beats.push(beat("code", "code", flights, `Code checks flagged ${plural(names.length, "flight")}`, { flights: names }));
  }
  const coord = run.filter((e) => COORD.has(e.type));
  const refused = coord.filter((e) => e.type === "refused" || e.type === "undone");
  const handed = coord.filter((e) => e.type === "handoff");
  if (coord.length) {
    const text = refused.length ? refused[refused.length - 1].text : handed.length ? `Coordinator handed out ${plural(handed.length, "job")}` : coord[coord.length - 1].text;
    // the jobs each skill was handed: they wait in line until that skill's beat plays
    const jobs = {};
    for (const e of handed) if (e.skill) jobs[e.skill] = (jobs[e.skill] || 0) + 1;
    beats.push(beat("coord", "coord", coord, text, { refused: refused.length > 0, jobs }));
  }
  // each skill the run reached, in the order of its first step
  const bySkill = new Map();
  for (const e of run) {
    if (!(e.type === "skill" || e.type === "skill-failed") || !e.skill) continue;
    if (!bySkill.has(e.skill)) bySkill.set(e.skill, []);
    bySkill.get(e.skill).push(e);
  }
  for (const [id, evs] of bySkill) {
    const failed = evs.every((e) => e.type === "skill-failed");
    beats.push(beat("skill", `sk-${id}`, evs, `${SKILL_NAME[id] || id}: ${failed ? "no result" : plural(evs.length, "step")}`, { skill: id, failed }));
  }
  // what reached a person: new drafts at the Desk, a skill's paper for the Desk, or must-do work
  const drafts = run.filter((e) => e.type === "desk" || (e.type === "skill" && e.toDesk));
  if (refused.length) {
    const must = refused[refused.length - 1].n || 0;
    // the hero says the count as it bumps: the beat line names the step, the screen reader hears both
    beats.push(beat("you", "you", refused, "To You decide", { must, say: `${plural(must, "must-do flight")} passed to you` }));
  } else if (drafts.length) {
    beats.push(beat("you", "you", drafts, `${plural(drafts.length, "draft")} reached the Desk for a person`));
  }
  const has = (k) => beats.some((b) => b.kind === k);
  const missing = [];
  if (!has("feeds")) missing.push("feed read");
  if (!has("coord")) missing.push("Coordinator run");
  else if (!refused.length && !has("skill")) missing.push("skill step");
  if (!has("you")) missing.push("step to You decide");
  return { beats, full: beats.length > 0 && !missing.length, missing };
}

// The newest full chain among the runs the page holds; with none, the newest chain as it is.
export function lastChain(M) {
  const ev = (M?.events || []).filter((e) => e.type !== "note" && e.type !== "onreq" && e.type !== "decided");
  let newest = null;
  let i = ev.length - 1;
  for (let tries = 0; tries < MAX_RUNS; tries++) {
    while (i >= 0 && !COORD.has(ev[i].type)) i--;
    if (i < 0) break;
    const run = runAt(ev, i);
    const chain = chainOf(ev, run);
    if (chain.full) return chain;
    newest = newest || chain;
    i = ev.indexOf(run[0]) - 1;
  }
  return newest || chainOf(ev, []);
}

// How long each beat of the catch-up shows: about CATCHUP_MS for the chain, one RM_STEP_MS each
// under reduced motion.
export function beatMs(n, rm = false) {
  if (rm) return RM_STEP_MS;
  return Math.round(Math.min(CATCHUP_MAX_MS, Math.max(CATCHUP_MIN_MS, CATCHUP_MS / Math.max(1, n))));
}

// What the panel says (screen readers only) under the player when the chain is not whole (never a stand-in step).
export function chainNote(chain) {
  if (!chain.beats.length) return "No steps held on this page yet to catch up on.";
  if (chain.full) return "";
  return "Showing the latest steps. Earlier ones ran before this page opened.";
}

// The events the panel shows during the catch-up: every event up to the chain's first beat that is
// not one of its beats (the replay's minute clock gives a tick's steps one time, so "before" is
// "at or before"), then the events of the beats played so far (`played`: their ids) in the order
// they played, so the log's newest row is the beat playing.
export function eventsShown(M, chain, played) {
  const first = chain.beats.length ? Math.min(...chain.beats.map((b) => b.from)) : Infinity;
  const inChain = new Map();
  chain.beats.forEach((b, i) => { for (const id of b.ids) if (!inChain.has(id)) inChain.set(id, i); });
  const evs = M?.events || [];
  const before = evs.filter((e) => !inChain.has(e.id) && e.at <= first);
  const playedEvs = evs.filter((e) => inChain.has(e.id) && played.has(e.id));
  playedEvs.sort((a, b) => inChain.get(a.id) - inChain.get(b.id) || a.at - b.at);
  return [...before, ...playedEvs];
}

// Each skill's row while the catch-up plays beat `i` of `chain`: its state before the chain (from
// the steps before it: "last" with its time, or "noresult"), "inline" with the jobs the
// Coordinator's beat handed it once that beat has played, "running" while its own beat plays, then
// "done" (or "noresult") with the beat's time. A skill the page holds no step of is absent: idle.
export function catchupSkills(M, chain, i) {
  const out = {};
  if (!chain?.beats.length) return out;
  const first = Math.min(...chain.beats.map((b) => b.from));
  const inChain = new Set(chain.beats.flatMap((b) => b.ids));
  for (const e of M?.events || []) {
    if (e.at > first || inChain.has(e.id) || !e.skill) continue;
    if (e.type === "skill" || e.type === "handoff") out[e.skill] = { state: "last", at: e.at };
    else if (e.type === "skill-failed") out[e.skill] = { state: "noresult", at: e.at };
  }
  const coordAt = chain.beats.findIndex((b) => b.kind === "coord");
  const jobs = coordAt >= 0 && coordAt <= i ? chain.beats[coordAt].jobs || {} : {};
  chain.beats.forEach((b, k) => {
    if (b.kind !== "skill") return;
    if (k < i) out[b.skill] = { state: b.failed ? "noresult" : "done", at: b.at };
    else if (k === i) out[b.skill] = { state: "running", at: b.at };
    else if (jobs[b.skill]) out[b.skill] = { state: "inline", n: jobs[b.skill] };
  });
  return out;
}

// The rows of those events, newest first, as the panel shows them.
export const rowsOf = (events) => foldRows(events).map(rowView).reverse();
