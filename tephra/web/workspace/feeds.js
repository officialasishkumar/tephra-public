// Workspace › Data feeds (/workspace/feeds): the tephra.airline/1 format, and the dry run: a file
// or pasted JSON checked record by record by the server's own push rules, with nothing taken in
// (POST /api/airline/feeds/dry-run), drawn by the shared dryrun.js (an airline's Feeds page on this
// site uses the same card, whose stamp says "DRY RUN · NOTHING TAKEN IN"). Refused records come
// first, with the validator's own reason.

import { el, icon } from "../wall/util.js";
import { mountDryRun } from "../dryrun.js";
import { PATHS } from "./api.js";

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

export function renderFeeds(main) {
  main.append(formatCard());
  mountDryRun(main, { path: PATHS.dryRun, note: "This is a check only. Freshness is checked against the current UTC time, as your own TEPHRA does. Pushes from airline accounts never enter the shared demo picture." });
  main.append(
    el("section", { class: "card wcard", "aria-labelledby": "real-h" },
      el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-network")), el("h2", { id: "real-h", text: "Sending for real" })),
      el("p", {}, "Run your own TEPHRA from the ", el("a", { class: "link", href: "/workspace/kit", dataset: { go: "" }, text: "setup kit" }), ", make a key on its Desk › Data connections, and point push.py at it.")));
}
