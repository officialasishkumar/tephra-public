// The demo's Assistant tab (SPEC v2 5.2.5): TEPHRA Assistant's steps in the side panel, from the
// same model as the /assistant board (board.js flowModel). Under the state line (panels.js
// renderChrome writes it): in REPLAY a player over the replay's steps, the five steps with the
// newest one ringed, the newest step as a "Now" card and every earlier step, newest first, under
// its minute. In REPLAY the panel plays the replay's steps, labelled as such; it is never only
// "paused". Every string goes in through el() (textContent); tick positions go through the CSSOM.

import { el, icon, reducedMotion } from "./util.js";
import { hmsOf, RESULT } from "./board.js";
import { stepsList, setCurrentStep, FIVE_STEPS } from "../five-steps.js";
import { visibleRows, minuteGroups, playerWords, trackTicks, newestAt, sayRow, STAGES, PLAY_SPEED, RM_STEP_MS } from "./assist.js";

const PAGE_ROWS = 60;
const SAY_EVERY_MS = 10000;
// a gap in the replay longer than this much screen time is skipped down to SKIP_TO_S
const SKIP_OVER_S = 1.2;
const SKIP_TO_S = 0.6;
const STAGE_ICON = Object.fromEntries(FIVE_STEPS.map((s) => [s.key, s.icon]));
const RESULT_OF = { done: RESULT.ok, tool: ["ok", "i-check", "Tool"], noresult: RESULT.failed };

const setText = (node, text) => { if (node.textContent !== text) node.textContent = text; };
const setAttr = (node, k, v) => { if (node.getAttribute(k) !== v) node.setAttribute(k, v); };
const stageNo = (stage) => STAGES.indexOf(stage) + 1;
const rowIcon = (r) => (r.actor === "Aircraft positions" || r.actor === "Airline positions" ? "i-aircraft" : STAGE_ICON[r.stage]);

function resultWord(r) {
  const [tone, ic, word] = RESULT_OF[r.result] || [];
  return word ? el("span", { class: `ev__res ev__res--${tone}` }, icon(ic), word) : null;
}

function logRow(r) {
  return el("li", { class: `ev t-${r.stage}` },
    el("time", { class: "ev__t", datetime: new Date(r.tm).toISOString(), text: hmsOf(r.tm) }),
    el("span", { class: "ev__ic" }, icon(rowIcon(r))),
    el("span", { class: "ev__who" }, r.actor, r.kind ? el("small", { text: r.kind }) : null, resultWord(r)),
    el("span", { class: "ev__what", text: r.text }));
}

export function mountAssist(host) {
  const player = host.querySelector("#assist-player");
  const nowCard = host.querySelector("#assist-now");
  const log = host.querySelector("#assist-log");
  const live = host.querySelector("#assist-live");
  const pipe = stepsList({ size: "sm", label: "Where the newest step is", id: "assist-pipe" });
  pipe.classList.add("as-pipe");
  host.querySelector("#assist-pipe").replaceWith(pipe);

  const playBtn = el("button", { type: "button", class: "player__btn" });
  const lead = el("b");
  const words = el("span", { class: "player__text" });
  const time = el("span", { class: "mono player__time" });
  const ticks = el("span", { class: "player__ticks", "aria-hidden": "true" });
  const knob = el("i", { class: "player__knob", "aria-hidden": "true" });
  const track = el("div", { class: "player__track", role: "slider", tabindex: "0", "aria-label": "Position in TEPHRA's steps", "aria-valuemin": "0", "aria-valuemax": "100" }, ticks, knob);
  player.replaceChildren(playBtn, el("p", { class: "player__words" }, lead, words, time), track);

  let M = null;
  const P = { mode: "follow", t: NaN, from: NaN, rm: reducedMotion() };
  let shown = PAGE_ROWS;
  let logKey = "", nowKey = "", tickKey = "", seenN = -1;
  let lastSaid = -1e9, sayTimer = 0, said = "";
  let raf = 0, lastFrame = 0, rmLeft = 0;

  const steps = () => (M?.events || []).filter((e) => !e.quiet && e.type !== "note");
  const eventsAt = (t) => (M?.events || []).reduce((n, e) => n + (e.at <= t ? 1 : 0), 0);
  const playhead = () => (P.mode === "follow" ? newestAt(M) : P.t);

  function renderPlayer() {
    player.hidden = !M;
    if (!M) return;
    const w = playerWords(M, P);
    setText(lead, w.lead);
    setText(words, w.text);
    setText(time, w.time || "");
    // LIVE: no player, one line
    player.classList.toggle("player--live", w.live);
    playBtn.hidden = w.live;
    track.hidden = w.live;
    if (w.live) return;
    const ic = w.action === "play" ? "i-play" : "i-pause";
    if (playBtn.dataset.icon !== ic) { playBtn.dataset.icon = ic; playBtn.replaceChildren(icon(ic)); }
    setAttr(playBtn, "aria-label", w.button);
    playBtn.title = w.button;
    setAttr(track, "aria-valuetext", w.valuetext);
    const s = steps();
    const t0 = s.length ? s[0].at : NaN, t1 = s.length ? s[s.length - 1].at : NaN;
    const frac = Number.isFinite(t0) && t1 > t0 ? Math.min(1, Math.max(0, (playhead() - t0) / (t1 - t0))) : 1;
    setAttr(track, "aria-valuenow", String(Math.round(frac * 100)));
    knob.style.setProperty("left", `${(frac * 100).toFixed(2)}%`);
    const tk = `${s.length}|${t0}|${t1}`;
    if (tk !== tickKey) {
      tickKey = tk;
      ticks.replaceChildren(...trackTicks(M).map((x) => {
        const i = el("i", { class: x.ai ? "is-ai" : "" });
        i.style.setProperty("left", `${(x.frac * 100).toFixed(2)}%`);
        return i;
      }));
    }
  }

  function say(r) {
    window.clearTimeout(sayTimer);
    const wait = Math.max(0, SAY_EVERY_MS - (performance.now() - lastSaid));
    sayTimer = window.setTimeout(() => {
      const text = sayRow(r);
      if (text === said) return;
      live.textContent = text;
      said = text;
      lastSaid = performance.now();
    }, wait);
  }

  function renderNowCard(r, first) {
    nowCard.hidden = !r;
    if (!r) { nowKey = ""; return; }
    const key = `${r.key}|${r.text}|${r.result}`;
    if (key === nowKey) return;
    const changed = nowKey !== "";
    nowKey = key;
    nowCard.replaceChildren(
      el("div", { class: "as-now__top" },
        el("span", { class: `as-now__badge t-${r.stage}` }, icon(rowIcon(r)), `${stageNo(r.stage)} · ${r.actor}`),
        r.kind ? el("small", { class: "as-now__kind", text: r.kind }) : null,
        resultWord(r),
        el("time", { class: "as-now__time mono", datetime: new Date(r.tm).toISOString(), text: hmsOf(r.tm) })),
      el("p", { class: "as-now__text", text: r.text }));
    if (changed && !first) {
      nowCard.classList.remove("is-fresh");
      void nowCard.offsetWidth; // restart the edge's fade
      nowCard.classList.add("is-fresh");
      if (P.mode === "follow") say(r);
    }
  }

  function renderLog(rows) {
    const rest = rows.slice(1, 1 + shown);
    const key = `${rows.length}|${shown}|${rest.map((r) => `${r.key}:${r.text}`).join("§")}`;
    if (key === logKey) return;
    logKey = key;
    if (!rows.length) {
      log.replaceChildren(el("p", { class: "log__empty", text: "No steps yet in this window." }));
      return;
    }
    const kids = minuteGroups(rest).flatMap((g) => [el("h3", { class: "log__min", text: g.minute }), el("ol", {}, ...g.rows.map(logRow))]);
    if (rows.length - 1 > shown) {
      kids.push(el("button", { type: "button", class: "link-btn log__more", dataset: { focus: "assist-older" }, text: "Show older steps" }));
    }
    log.replaceChildren(...kids);
  }

  function render(first = false) {
    renderPlayer();
    const t = playhead();
    const rows = Number.isFinite(t) ? visibleRows(M, t) : [];
    seenN = eventsAt(t);
    setCurrentStep(pipe, rows[0]?.stage || null);
    renderNowCard(rows[0] || null, first);
    renderLog(rows);
  }

  // ---- the player: follow (every step up to the newest), paused at the playhead, playing forward
  function setMode(mode, t = P.t) {
    P.mode = mode;
    P.t = t;
    if (mode === "playing") { P.from = t; lastFrame = 0; rmLeft = RM_STEP_MS; if (!raf) raf = requestAnimationFrame(frame); }
    render();
  }
  function frame(ts) {
    raf = 0;
    if (P.mode !== "playing" || !M) return;
    const dt = lastFrame ? Math.min(0.25, (ts - lastFrame) / 1000) : 0;
    lastFrame = ts;
    const s = steps();
    const end = newestAt(M);
    if (P.rm) {
      rmLeft -= dt * 1000;
      if (rmLeft <= 0) { rmLeft = RM_STEP_MS; P.t = s.find((e) => e.at > P.t)?.at ?? end; }
    } else {
      const next = s.find((e) => e.at > P.t);
      const gap = next ? (next.at - P.t) / (PLAY_SPEED * 1000) : 0;
      if (next && gap > SKIP_OVER_S) P.t = next.at - SKIP_TO_S * PLAY_SPEED * 1000;
      P.t += dt * 1000 * PLAY_SPEED;
    }
    if (!Number.isFinite(end) || P.t >= end) { setMode("follow", NaN); return; }
    if (eventsAt(P.t) !== seenN) render();
    else renderPlayer();
    raf = requestAnimationFrame(frame);
  }

  playBtn.addEventListener("click", () => {
    if (P.mode === "playing") setMode("paused", P.t);
    else if (P.mode === "follow") setMode("paused", newestAt(M));
    else {
      const s = steps();
      setMode("playing", P.t >= newestAt(M) && s.length ? s[0].at : P.t);
    }
  });
  track.addEventListener("pointerdown", (ev) => {
    const s = steps();
    if (s.length < 2) return;
    const r = track.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (ev.clientX - r.left) / Math.max(1, r.width)));
    setMode("playing", s[0].at + frac * (s[s.length - 1].at - s[0].at));
  });
  track.addEventListener("keydown", (ev) => {
    const s = steps();
    if (!s.length) return;
    const t = playhead();
    let to = null;
    if (ev.key === "ArrowRight") to = s.find((e) => e.at > t)?.at ?? null;
    else if (ev.key === "ArrowLeft") to = [...s].reverse().find((e) => e.at < t)?.at ?? null;
    else if (ev.key === "Home") to = s[0].at;
    else if (ev.key === "End") { ev.preventDefault(); setMode("follow", NaN); return; }
    else if (ev.key === " ") { ev.preventDefault(); playBtn.click(); return; }
    else return;
    ev.preventDefault();
    if (to != null) setMode("paused", to);
  });
  log.addEventListener("click", (ev) => {
    if (!ev.target.closest(".log__more")) return;
    shown += PAGE_ROWS;
    render();
  });
  window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => { P.rm = reducedMotion(); render(); });

  return {
    update(model, { conn = null } = {}) {
      const first = !M;
      M = model?.ready ? model : null;
      log.classList.toggle("is-stale", !!conn?.lostAt);
      render(first);
    },
  };
}
