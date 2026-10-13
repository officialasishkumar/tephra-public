// A photo for the map's card (UI-DESIGN 7.23): Wikidata's image (P18) of a volcano, found by its
// Smithsonian volcano number (P1886), or of an airport, found by its ICAO code (P239). It is shown
// only when Wikimedia Commons says its licence is free (public domain, CC0, CC BY, CC BY-SA), with
// its author and licence under it and a link to its Commons page. No match, no free licence or a
// failed read: no photo, and nothing in its place. Planes get none (the type is rarely known, and a
// real airline's livery is not TEPHRA's to show). Read from the browser; nothing is stored.

import { el, safeExternalUrl } from "./util.js";

const SPARQL = "https://query.wikidata.org/sparql";
const COMMONS = "https://commons.wikimedia.org/w/api.php";
const PROP = { volcano: "P1886", airport: "P239" };
const FREE = /^(public domain|pd\b|cc0|cc[ -]by(-sa)?\b)/i;
const HOSTS = ["https://upload.wikimedia.org/", "https://thumb.wikimedia.org/"];
const cache = new Map();

async function getJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(6000) });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

// Commons' author field is HTML: only its text is kept.
const textOf = (html) => new DOMParser().parseFromString(String(html || ""), "text/html").body.textContent.trim().replace(/\s+/g, " ");

async function lookup(kind, code) {
  const id = String(code).replace(/"/g, "");
  const q = `SELECT ?img WHERE { ?x wdt:${PROP[kind]} "${id}"; wdt:P18 ?img } LIMIT 1`;
  const found = await getJson(`${SPARQL}?format=json&query=${encodeURIComponent(q)}`);
  const uri = found?.results?.bindings?.[0]?.img?.value;
  if (!uri) return null;
  const file = decodeURIComponent(uri.split("/Special:FilePath/")[1] || "");
  if (!file) return null;
  const info = await getJson(`${COMMONS}?action=query&format=json&origin=*&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=560&titles=${encodeURIComponent(`File:${file}`)}`);
  const page = Object.values(info?.query?.pages || {})[0];
  const ii = page?.imageinfo?.[0];
  const licence = ii?.extmetadata?.LicenseShortName?.value || "";
  const src = safeExternalUrl(ii?.thumburl);
  if (!src || !HOSTS.some((h) => src.startsWith(h)) || !FREE.test(licence)) return null;
  const author = textOf(ii.extmetadata?.Artist?.value) || "Unknown author";
  return { src, licence, author: author.length > 60 ? `${author.slice(0, 57)}…` : author, href: safeExternalUrl(ii.descriptionurl) };
}

export function photoFor(kind, code) {
  if (!PROP[kind] || !code) return Promise.resolve(null);
  const key = `${kind}:${code}`;
  if (!cache.has(key)) cache.set(key, lookup(kind, code).catch(() => null));
  return cache.get(key);
}

export function photoFigure(photo, alt) {
  return el("figure", { class: "mcard__photo" },
    el("img", { src: photo.src, alt, loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" }),
    el("figcaption", {},
      photo.href ? el("a", { href: photo.href, target: "_blank", rel: "noopener", text: `Photo: ${photo.author} · ${photo.licence}` }) : `Photo: ${photo.author} · ${photo.licence}`));
}
