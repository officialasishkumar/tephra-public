// Where a page's API and in-app links point (SPEC-FINAL 5.9). Under /a/<ICAO>/ (a hosted airline's
// own space) every API call goes to /a/<ICAO>/api/... and the in-app links to the Desk, the map and
// documents stay inside the space; everywhere else nothing changes. Links to /guide, /privacy and
// blob URLs stay at the root.

const TENANT_PATH = /^\/a\/([A-Z]{3})(?:\/|$)/;

// The ICAO of the space a path is in, or null.
export function tenantOf(pathname) {
  const m = TENANT_PATH.exec(String(pathname || ""));
  return m ? m[1] : null;
}

// The mapping for one path; the module's own exports are this for the page's location.
export function baseFor(pathname) {
  const tenant = tenantOf(pathname);
  const pageBase = tenant ? `/a/${tenant}` : "";
  const api = (path) => `${pageBase}/api${path}`;
  const page = (path) => {
    const p = String(path);
    if (!tenant) return p;
    if (p === "/desk" || p.startsWith("/desk#") || p.startsWith("/desk?")) return pageBase + p;
    if (p === "/demo") return `${pageBase}/`;
    if (p.startsWith("/demo#") || p.startsWith("/demo?")) return `${pageBase}/${p.slice(5)}`;
    if (p.startsWith("/docs/")) return pageBase + p;
    return p;
  };
  // a root API path ("/api/state?x=1") asked of the space: the Desk's path tables stay the demo's
  const tenantPath = (path) => (tenant && /^\/api\//.test(path) ? pageBase + path : path);
  return { TENANT: tenant, PAGE_BASE: pageBase, api, page, tenantPath };
}

const here = baseFor(globalThis.location ? globalThis.location.pathname : "");

export const TENANT = here.TENANT;
export const PAGE_BASE = here.PAGE_BASE;
export const api = here.api;
export const page = here.page;
export const tenantPath = here.tenantPath;

// tephra.config.SHADOW_WORDS (a test keeps them equal)
export const SHADOW_WORDS = "Shadow · not for use";

const IN_APP = /^\/(?:desk(?:$|[#?])|demo(?:$|[#?])|docs\/)/;

// The static links of a page shell (index.html, desk.html, doc.html) moved into the space.
export function rewriteLinks(root, map = page) {
  for (const a of root.querySelectorAll("a[href]")) {
    const href = a.getAttribute("href");
    if (IN_APP.test(href)) a.setAttribute("href", map(href));
  }
}
