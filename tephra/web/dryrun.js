// The dry run of a tephra.airline/1 push, shared by Workspace › Data feeds and an airline's Feeds
// page: a file or pasted JSON checked record by record by the server's own push rules, with
// nothing taken in. Refused records come first, with the validator's own reason.
// mountDryRun(container, { path, label?, info? }) appends one card to `container`; `path` is the
// dry-run route (POST, raw JSON body), `label` the card's heading and `info` what the (i) beside the
// stamp says (the card says nothing more: owner, 17 Oct, "say less").

import { el, icon } from "./wall/util.js";
import { infoButton } from "./wall/info.js";
import { segmented } from "./onboard/form.js";
import { call, errorCode, failWords, minutesWords, retryMinutes } from "./workspace/api.js";

export const MAX_BYTES = 512 * 1024;
export const DRY_RUN_STAMP = "DRY RUN · NOTHING TAKEN IN";
const SECTIONS = [["positions", "positions"], ["flight_plans", "flight plans"], ["pilot_reports", "pilot reports"]];
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
};

export function resultView(name, r) {
  const total = SECTIONS.reduce((n, [k]) => n + (r[k]?.total || 0), 0);
  const tiles = SECTIONS.map(([k, plural]) => {
    const s = r[k] || { total: 0, accepted: 0 };
    const refused = s.total - s.accepted;
    return el("div", { class: "vstat" },
      el("b", {}, String(s.accepted), el("small", { text: ` / ${s.total}` })),
      el("span", {}, `${plural} accepted`, refused ? [" · ", el("em", { text: `${refused} refused` })] : null, k === "pilot_reports" ? " · checked for shape only" : null));
  });
  const accepted = Array.isArray(r.accepted) ? r.accepted : [];
  const rejected = Array.isArray(r.rejected) ? r.rejected : [];
  const notes = accepted.filter((a) => a.note).length;
  return [
    el("p", { class: "vres__file" }, el("b", { text: name }), ` · ${total} ${total === 1 ? "record" : "records"} · checked ${hhmm(r.checked_at)}`),
    el("div", { class: "vres__sum" }, ...tiles),
    rejected.length
      ? el("ul", { class: "vrows", "aria-label": "Refused records" }, ...rejected.map((p) => el("li", {},
        icon("i-x", "icon bad"), el("span", { class: "sr-only", text: "Refused: " }),
        el("code", { text: `${p.section}[${p.index}]` }),
        el("span", { text: p.reason }))))
      : null,
    notes ? el("p", { class: "status status--caution" }, icon("st-caution"), el("span", { text: `${notes} ${notes === 1 ? "position would be taken but not checked" : "positions would be taken but not checked"} against the ash: no airline-style callsign.` })) : null,
    accepted.length
      ? el("details", { class: "help" },
        el("summary", {}, el("span", { text: `Show ${accepted.length} accepted ${accepted.length === 1 ? "record" : "records"}` }), icon("i-chevron-down", "icon chev")),
        el("ul", { class: "vrows" }, ...accepted.map((a) => el("li", {},
          icon("i-check", "icon ok"), el("span", { class: "sr-only", text: "Accepted: " }),
          el("code", { text: `${a.section}[${a.index}]` }),
          el("span", {}, a.text, a.note ? el("small", { class: "vrows__note", text: ` · ${a.note}` }) : null)))))
      : null,
  ].filter(Boolean);
}

// The words for a refused dry run (no result to show).
export function failText(res) {
  if (res.status === 422 && errorCode(res) === "not_a_push") return `This file is not a tephra.airline/1 push: ${res.data?.detail || "no detail"}.`;
  if (res.status === 429) return `Too many dry runs this hour. Try again in about ${minutesWords(retryMinutes(res))}.`;
  if (res.status === 413) return "This file is larger than 512 KB.";
  return failWords(res);
}

// One error line: a file that needs fixing says so in caution with the triangle; an alarm (offline,
// a server failure) in red with the octagon. Always the words.
const errLine = (text, alarm = false) =>
  el("p", { class: alarm ? "err err--alarm" : "err" }, icon(alarm ? "st-serious" : "st-caution"), el("span", { text }));

let mounted = 0;

export function mountDryRun(container, { path, label = "Dry run", info = "A check only: freshness uses the current UTC time." } = {}) {
  const ns = mounted ? `dr${mounted}` : "dr";
  mounted += 1;
  let tab = "upload";
  const result = el("div", { id: `${ns}-result`, class: "vres", "aria-live": "polite" });
  const check = async (textIn, name) => {
    if (new TextEncoder().encode(textIn).length > MAX_BYTES) {
      result.replaceChildren(errLine("This file is larger than 512 KB."));
      return;
    }
    try {
      JSON.parse(textIn);
    } catch (e) {
      result.replaceChildren(errLine(`This is not JSON: ${e.message}`));
      return;
    }
    result.replaceChildren(el("p", { class: "body2", text: "Checking…" }));
    const res = await call(path, { method: "POST", raw: textIn });
    if (res.ok && res.data) {
      result.replaceChildren(...resultView(name, res.data));
      return;
    }
    // offline or a server failure is an alarm (red, octagon); a file to fix is caution (triangle)
    result.replaceChildren(errLine(failText(res), res.status === 0 || res.status >= 500));
  };
  const panel = el("div", { id: `${ns}-tab-panel`, role: "tabpanel" });
  const draw = () => {
    panel.setAttribute("aria-labelledby", `${ns}-tab-${tab}`);
    if (tab === "upload") {
      const file = el("input", { type: "file", id: `${ns}-file`, accept: ".json,application/json", class: "sr-only" });
      file.addEventListener("change", async () => {
        const one = file.files?.[0];
        file.value = "";
        if (!one) return;
        if (one.size > MAX_BYTES) {
          result.replaceChildren(errLine("This file is larger than 512 KB."));
          return;
        }
        check(await one.text(), one.name);
      });
      const drop = el("div", { class: "drop" },
        el("span", { class: "drop__ic" }, icon("i-file")),
        el("p", { text: "Drop a .json file, up to 512 KB." }),
        el("label", { class: "btn btn--secondary", for: `${ns}-file` }, icon("i-file"), el("span", { text: "Choose a file" })), file);
      drop.addEventListener("dragover", (e) => {
        e.preventDefault();
        drop.classList.add("is-over");
      });
      drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
      drop.addEventListener("drop", async (e) => {
        e.preventDefault();
        drop.classList.remove("is-over");
        const one = e.dataTransfer?.files?.[0];
        if (one) check(await one.text(), one.name);
      });
      panel.replaceChildren(drop);
    } else {
      const area = el("textarea", { id: `${ns}-paste`, class: "input textarea mono", rows: "8", spellcheck: "false", placeholder: '{"format": "tephra.airline/1", "positions": [ … ]}' });
      const go = el("button", { type: "button", class: "btn btn--primary" }, el("span", { text: "Check" }));
      go.addEventListener("click", () => check(area.value, "Pasted JSON"));
      panel.replaceChildren(el("div", { class: "field" }, el("label", { for: `${ns}-paste`, text: "Paste a push" }), area), el("div", { class: "tool" }, go));
    }
  };
  const tabs = el("div", {});
  const drawTabs = () => {
    tabs.replaceChildren(segmented({
      label: "How to give the file", idBase: `${ns}-tab`, value: tab,
      tabs: [{ key: "upload", text: "Upload", icon: "i-file" }, { key: "paste", text: "Paste", icon: "i-clipboard" }],
      onChange: (k) => {
        tab = k;
        drawTabs();
        draw();
        document.getElementById(`${ns}-tab-${k}`)?.focus();
      },
    }));
  };
  drawTabs();
  draw();
  const card = el("section", { class: "card wcard", "aria-labelledby": `${ns}-h` },
    el("div", { class: "wcard__h wcard__h--stamp" },
      el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-check")),
      el("h2", { id: `${ns}-h`, text: label }),
      el("span", { class: "chipinfo" }, el("span", { class: "stamp", text: DRY_RUN_STAMP }),
        info ? infoButton({ topic: "the dry run", label: "About the dry run", text: info }) : null)),
    tabs, panel, result);
  container.append(card);
  return card;
}
