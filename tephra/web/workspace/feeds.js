// Workspace › Data feeds (/workspace/feeds): the tephra.airline/1 format, and the dry run: a file
// or pasted JSON checked record by record by the server's own push rules, with nothing taken in
// (POST /api/airline/feeds/dry-run). Refused records come first, with the validator's own reason.

import { el, icon } from "../wall/util.js";
import { segmented } from "../onboard/form.js";
import { PATHS, call, errorCode, failWords, minutesWords, retryMinutes } from "./api.js";

const MAX_BYTES = 512 * 1024;
const SECTIONS = [["positions", "positions", "position"], ["flight_plans", "flight plans", "flight plan"], ["pilot_reports", "pilot reports", "pilot report"]];
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
};

function formatCard() {
  return el("section", { class: "card wcard", "aria-labelledby": "fmt-h" },
    el("div", { class: "wcard__h" },
      el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-code")),
      el("h2", { id: "fmt-h", text: "The format" }),
      el("a", { class: "link", href: PATHS.schema, download: "" }, el("span", { text: "Schema (JSON)" }), icon("i-external-link"))),
    el("p", {}, "One JSON push, ", el("code", { text: 'format: "tephra.airline/1"' }), ", with any of three sections. Each record is checked on its own, so one bad record never refuses the rest."),
    el("dl", { class: "kv kv--fmt" },
      el("dt", {}, el("code", { text: "positions" })), el("dd", { text: "up to 1,000 · ICAO address, position, pressure altitude, observed_at" }),
      el("dt", {}, el("code", { text: "flight_plans" })), el("dd", { text: "up to 1,000 · flight, route, times" }),
      el("dt", {}, el("code", { text: "pilot_reports" })), el("dd", { text: "up to 20 · where and when a crew saw ash" })),
    el("p", { text: "observed_at must be within 5 minutes of your TEPHRA's clock; push.py stamps it at send time for positions measured just then." }));
}

function resultView(name, r) {
  const total = SECTIONS.reduce((n, [k]) => n + (r[k]?.total || 0), 0);
  const tiles = SECTIONS.map(([k, plural]) => {
    const s = r[k] || { total: 0, accepted: 0 };
    const refused = s.total - s.accepted;
    return el("div", { class: "vstat" },
      el("b", {}, String(s.accepted), el("small", { text: ` / ${s.total}` })),
      el("span", {}, `${plural} accepted`, refused ? [" · ", el("em", { text: `${refused} refused` })] : null, k === "pilot_reports" ? " · checked for shape only" : null));
  });
  const notes = r.accepted.filter((a) => a.note).length;
  return [
    el("p", { class: "vres__file" }, el("b", { text: name }), ` · ${total} ${total === 1 ? "record" : "records"} · checked ${hhmm(r.checked_at)}`),
    el("div", { class: "vres__sum" }, ...tiles),
    r.rejected.length
      ? el("ul", { class: "vrows", "aria-label": "Refused records" }, ...r.rejected.map((p) => el("li", {},
        icon("i-x", "icon bad"), el("span", { class: "sr-only", text: "Refused: " }),
        el("code", { text: `${p.section}[${p.index}]` }),
        el("span", { text: p.reason }))))
      : null,
    notes ? el("p", { class: "status status--caution" }, icon("st-caution"), el("span", { text: `${notes} ${notes === 1 ? "position would be taken but not checked" : "positions would be taken but not checked"} against the ash: no airline-style callsign.` })) : null,
    r.accepted.length
      ? el("details", { class: "help" },
        el("summary", {}, el("span", { text: `Show ${r.accepted.length} accepted ${r.accepted.length === 1 ? "record" : "records"}` }), icon("i-chevron-down", "icon chev")),
        el("ul", { class: "vrows" }, ...r.accepted.map((a) => el("li", {},
          icon("i-check", "icon ok"), el("span", { class: "sr-only", text: "Accepted: " }),
          el("code", { text: `${a.section}[${a.index}]` }),
          el("span", {}, a.text, a.note ? el("small", { class: "vrows__note", text: ` · ${a.note}` }) : null)))))
      : null,
  ];
}

export function renderFeeds(main) {
  let tab = "upload";
  const result = el("div", { id: "dr-result", class: "vres", "aria-live": "polite" });
  const check = async (textIn, name) => {
    if (new TextEncoder().encode(textIn).length > MAX_BYTES) {
      result.replaceChildren(el("p", { class: "err", text: "This file is larger than 512 KB." }));
      return;
    }
    try {
      JSON.parse(textIn);
    } catch (e) {
      result.replaceChildren(el("p", { class: "err" }, icon("i-alert"), el("span", { text: `This is not JSON: ${e.message}` })));
      return;
    }
    result.replaceChildren(el("p", { class: "body2", text: "Checking…" }));
    const res = await call(PATHS.dryRun, { method: "POST", raw: textIn });
    if (res.ok && res.data) {
      result.replaceChildren(...resultView(name, res.data).filter(Boolean));
      return;
    }
    const words = res.status === 422 && errorCode(res) === "not_a_push"
      ? `This file is not a tephra.airline/1 push: ${res.data?.detail || "no detail"}.`
      : res.status === 429 ? `Too many dry runs this hour. Try again in about ${minutesWords(retryMinutes(res))}.`
        : res.status === 413 ? "This file is larger than 512 KB." : failWords(res);
    result.replaceChildren(el("p", { class: "err" }, icon("i-alert"), el("span", { text: words })));
  };
  const panel = el("div", { id: "dr-tab-panel", role: "tabpanel" });
  const draw = () => {
    panel.setAttribute("aria-labelledby", `dr-tab-${tab}`);
    if (tab === "upload") {
      const file = el("input", { type: "file", id: "dr-file", accept: ".json,application/json", class: "sr-only" });
      file.addEventListener("change", async () => {
        const one = file.files?.[0];
        file.value = "";
        if (!one) return;
        if (one.size > MAX_BYTES) {
          result.replaceChildren(el("p", { class: "err", text: "This file is larger than 512 KB." }));
          return;
        }
        check(await one.text(), one.name);
      });
      const drop = el("div", { class: "drop" },
        el("span", { class: "drop__ic" }, icon("i-file")),
        el("p", {}, el("b", { text: "A tephra.airline/1 file" }), el("br"), ".json, up to 512 KB, read in this browser and checked by the server; nothing is taken in."),
        el("label", { class: "btn btn--secondary", for: "dr-file" }, icon("i-file"), el("span", { text: "Choose a file" })), file);
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
      const area = el("textarea", { id: "dr-paste", class: "input textarea mono", rows: "8", spellcheck: "false", placeholder: '{"format": "tephra.airline/1", "positions": [ … ]}' });
      const go = el("button", { type: "button", class: "btn btn--primary" }, el("span", { text: "Check" }));
      go.addEventListener("click", () => check(area.value, "Pasted JSON"));
      panel.replaceChildren(el("div", { class: "field" }, el("label", { for: "dr-paste", text: "Paste a push" }), area), el("div", { class: "tool" }, go));
    }
  };
  const tabs = el("div", {});
  const drawTabs = () => {
    tabs.replaceChildren(segmented({
      label: "How to give the file", idBase: "dr-tab", value: tab,
      tabs: [{ key: "upload", text: "Upload", icon: "i-file" }, { key: "paste", text: "Paste", icon: "i-clipboard" }],
      onChange: (k) => {
        tab = k;
        drawTabs();
        draw();
        document.getElementById(`dr-tab-${k}`)?.focus();
      },
    }));
  };
  drawTabs();
  draw();
  main.append(
    formatCard(),
    el("section", { class: "card wcard", "aria-labelledby": "dr-h" },
      el("div", { class: "wcard__h wcard__h--stamp" },
        el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-check")),
        el("h2", { id: "dr-h", text: "Dry run" }),
        el("span", { class: "stamp", text: "DRY RUN · NOTHING TAKEN IN" })),
      tabs, panel, result,
      el("p", { class: "body2", text: "This is a check only. Freshness is checked against the current UTC time, as your own TEPHRA does. Pushes from airline accounts never enter the shared demo picture." })),
    el("section", { class: "card wcard", "aria-labelledby": "real-h" },
      el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-network")), el("h2", { id: "real-h", text: "Sending for real" })),
      el("p", {}, "Run your own TEPHRA from the ", el("a", { class: "link", href: "/workspace/kit", dataset: { go: "" }, text: "setup kit" }), ", make a key on its Desk › Data connections, and point push.py at it.")));
}
