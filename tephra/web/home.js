// Home (SPEC-v2 5.1): words the two choices from /api/state, shows the onboarding parts only while
// the server shows onboarding, and swaps the second choice for the workspace when an airline is
// signed in. Every word goes in through el() / textContent.

import { $, el, icon } from "./wall/util.js";
import { setFeatures, has, applyFeatureNav } from "./wall/features.js";
import { initAccountNav } from "./account-nav.js";
import { volcanoOf, replayDay } from "./replay-words.js";

// The replay frame the map images show, written by scripts/capture_home_map.mjs with the images
// (home/replay-map.webp, home/replay-map-phone.webp): the replay clock and the case at capture.
const MAP_FRAME = { at: "10:33", case: "Anak Krakatau, 5 Sep 2026" };

async function getState() {
  try {
    const res = await fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

function demoLine(state) {
  if (!state) return "No sign-in";
  if (state.mode !== "REPLAY") return "The live picture, from public feeds · no sign-in";
  if (state.replay?.synthetic) return "A replay of invented demo data · no sign-in";
  const v = volcanoOf(state.replay);
  const day = replayDay(state.replay);
  if (v) return `A replay of ${[v, day].filter(Boolean).join(", ")} · no sign-in`;
  return day ? `A replay from ${day} · no sign-in` : "A replay · no sign-in";
}

function demoPills(state) {
  const replay = state?.mode === "REPLAY";
  return [
    replay && el("span", { class: "go__pill go__pill--replay" }, icon("i-replay"), "Replay"),
    el("span", { class: "go__pill", text: "Ring of Fire Air, a fictional airline" }),
  ];
}

// The live count says it is live: the picture is one captured frame, so an unlabelled number over
// it would disagree with the flights it draws.
function showCount(state) {
  const n = state?.mode === "REPLAY" ? state.exposed_count : null;
  const shown = Number.isInteger(n) && n > 0;
  $("home-count").hidden = !shown;
  if (shown) {
    $("home-count").replaceChildren(
      el("span", { class: "home__count-now", text: "Now in the replay" }),
      el("b", { text: n }),
      el("span", { text: `RFA flight${n === 1 ? "" : "s"} in or heading in` }));
  }
  document.title = shown ? "REPLAY - TEPHRA" : "TEPHRA";
}

function showWorkspace(account) {
  const tile = $("go-onboard");
  tile.setAttribute("href", "/workspace");
  $("go-onboard-t").textContent = "Your airline workspace";
  $("go-onboard-sub").textContent = [account.icao, account.name].filter(Boolean).join(" · ");
  for (const p of document.querySelectorAll(".home__signin")) p.hidden = true;
}

async function main() {
  $("home-cap-t").textContent = `Map from the replay at ${MAP_FRAME.at} UTC · ${MAP_FRAME.case}`;
  const state = await getState();
  setFeatures(state?.features);
  applyFeatureNav();
  for (const part of document.querySelectorAll("main [data-feature]")) part.hidden = !has(part.dataset.feature);
  $("go-demo-sub").textContent = demoLine(state);
  $("go-demo-pills").replaceChildren(...demoPills(state).filter(Boolean));
  showCount(state);
  const account = await initAccountNav({ right: $("tn-right"), signin: false });
  if (account.signedIn && has("onboard")) showWorkspace(account);
}

main();
