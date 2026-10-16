// The optional features the server shows (SystemState.features, TEPHRA_FEATURES). Hidden features keep
// their code; the nav, menus, legend rows, index rows and board cards consult has(). A nav link names
// its feature in data-feature and shows only when the feature is on, or when it is the page you are on.
let shown = new Set();
export function setFeatures(list) { shown = new Set(Array.isArray(list) ? list : []); }
export const has = (name) => shown.has(name);
export function applyFeatureNav(root = document) {
  for (const a of root.querySelectorAll(".topnav a[data-feature]"))
    a.hidden = !has(a.dataset.feature) && a.getAttribute("aria-current") !== "page";
}
