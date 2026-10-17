// Home (SPEC-v2 5.1): shows the onboarding parts only while the server shows onboarding, swaps the
// second choice for the workspace when an airline is signed in, puts Sign in in the top bar while
// signed out (the server says when accounts are on), and draws the five steps: a
// picture beside the choices (home/how.js) and a strip under the line on narrow screens. Neither
// carries data. The two choices are titles only (owner, 16 Oct 2026: "no need to mention it
// here"); the demo says it is a replay itself. Every word goes in through el() / textContent.

import { $ } from "./wall/util.js";
import { setFeatures, has, applyFeatureNav } from "./wall/features.js";
import { initAccountNav } from "./account-nav.js";
import { stepsList } from "./five-steps.js";
import { howPicture } from "./home/how.js";
import { driftAsh } from "./home/ash.js";

async function getState() {
  try {
    const res = await fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

function showWorkspace() {
  const tile = $("go-onboard");
  tile.setAttribute("href", "/workspace");
  $("go-onboard-t").textContent = "Your airline workspace";
}

// The pictures' pulses stop while the tab is hidden (home.css .is-paused); the ash stops itself.
function drawPictures() {
  howPicture($("home-how"));
  $("home-strip").replaceChildren(stepsList({ size: "sm" }));
  driftAsh($("home-ash"));
  const pause = () => document.body.classList.toggle("is-paused", document.hidden);
  document.addEventListener("visibilitychange", pause);
  pause();
}

async function main() {
  drawPictures();
  const state = await getState();
  setFeatures(state?.features);
  applyFeatureNav();
  for (const part of document.querySelectorAll("main [data-feature]")) part.hidden = !has(part.dataset.feature);
  const account = await initAccountNav({ right: $("tn-right"), signin: has("onboard") });
  if (account.signedIn && has("onboard")) showWorkspace();
}

main();
