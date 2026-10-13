// The guide page (UI-DESIGN 7.22): Help, About and the operator policy, built from the same builders
// the Wall's dialogs used. Everything goes in through el() (textContent). The two reads are public
// GETs; a policy that does not load says so in its own section.

import { el } from "./wall/util.js";
import { helpContent, aboutContent } from "./wall/controls.js";
import { policyDialog } from "./wall/policy.js";

async function getJson(path) {
  try {
    const res = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

const section = (id, title, body) => el("section", { id, class: "guide__sec", "aria-labelledby": `${id}-h` },
  el("h2", { id: `${id}-h`, class: "guide__h", text: title }), body);

async function build() {
  const [state, policy] = await Promise.all([getJson("/api/state"), getJson("/api/policy")]);
  if (state?.disclaimer) document.querySelector(".guide__honesty strong").textContent = state.disclaimer;
  document.getElementById("guide").replaceChildren(
    section("read", "Read the map", helpContent(false, { page: true })),
    section("about", "About TEPHRA", aboutContent(state, undefined, { page: true })),
    section("policy", "Operator policy", policyDialog(policy)));
  // a link to a section (/guide#help-key) lands on it once the page is built
  const at = location.hash && document.getElementById(location.hash.slice(1));
  if (at) at.scrollIntoView({ block: "start" });
}

build();
