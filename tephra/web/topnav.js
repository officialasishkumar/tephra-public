// The shared header's nav on pages without a script of their own (privacy, documents): the server's
// feature set hides the Onboard link the same way the other pages do, and a signed-in airline's
// Onboard link becomes Workspace.
import { setFeatures, applyFeatureNav } from "./wall/features.js";
import { initAccountNav } from "./account-nav.js";

fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store" })
  .then((res) => (res.ok ? res.json() : null))
  .catch(() => null)
  .then((state) => { setFeatures(state?.features); applyFeatureNav(); return initAccountNav(); });
