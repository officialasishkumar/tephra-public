// The shared header's nav on pages without a script of their own (privacy, documents): the server's
// feature set hides the Connect link the same way the Wall, the Desk and the Guide do.
import { setFeatures, applyFeatureNav } from "./wall/features.js";

fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store" })
  .then((res) => (res.ok ? res.json() : null))
  .catch(() => null)
  .then((state) => { setFeatures(state?.features); applyFeatureNav(); });
