// Workspace › Data feeds (/workspace/feeds): the tephra.airline/1 format, and the dry run: a file
// or pasted JSON checked record by record by the server's own push rules, with nothing taken in
// (POST /api/airline/feeds/dry-run), drawn by the shared dryrun.js (an airline's Feeds page on this
// site uses the same card, whose stamp says "DRY RUN · NOTHING TAKEN IN"). Refused records come
// first, with the validator's own reason.

import { el, icon } from "../wall/util.js";
import { mountDryRun } from "../dryrun.js";
import { caret } from "../onboard/form.js";
import { PATHS } from "./api.js";

// The format, closed until asked for: the shape, then the three sections.
function formatCard() {
  return el("details", { class: "card wcard wfold", "aria-labelledby": "fmt-h" },
    el("summary", {},
      el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-code")),
      el("h2", { id: "fmt-h", text: "The format" }), caret()),
    el("p", {}, "One JSON push, ", el("code", { text: "tephra.airline/1" }), ", up to three sections. Each record is checked alone. ",
      el("a", { class: "link", href: PATHS.schema, download: "" }, el("span", { text: "Schema (JSON)" }), icon("i-external-link"))),
    el("dl", { class: "kv kv--fmt" },
      el("dt", {}, el("code", { text: "positions" })), el("dd", { text: "up to 1,000 · ICAO address, position, pressure altitude, observed_at (within 5 minutes)" }),
      el("dt", {}, el("code", { text: "flight_plans" })), el("dd", { text: "up to 1,000 · flight, route, times" }),
      el("dt", {}, el("code", { text: "pilot_reports" })), el("dd", { text: "up to 20 · where and when a crew saw ash" })));
}

export function renderFeeds(main) {
  main.append(formatCard());
  mountDryRun(main, { path: PATHS.dryRun, info: "A check only: freshness uses the current UTC time. Pushes from airline accounts never enter the shared demo picture." });
}
