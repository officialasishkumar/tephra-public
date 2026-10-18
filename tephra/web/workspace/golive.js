// Workspace › Overview, "Go live on TEPHRA" (SPEC hosted §5.1): once this site hosts airlines, a
// verified airline sets up its own space at /a/<ICAO>/, ticks the four-item checklist, starts in
// SHADOW (every draft says "Shadow · not for use"), and its ops manager switches to LIVE, goes
// back to SHADOW or stops; TEPHRA staff may suspend it. The cards read GET /api/hosted/me
// and, for the airline's own space, its TenantHeader and GoLive. Buttons that change the space are
// drawn for ops managers only, and a Start that cannot run says why. Each card says one short line
// per fact; what explains it sits behind the shared (i) (wall/info.js). Form errors are terse and
// wait until a typed field is left or the form is sent. Every string goes in through el()
// (textContent).

import { el, icon } from "../wall/util.js";
import { ruleMessage } from "../onboard/pages.js";
import { checkOnLeave, field, infoTail, input, setError } from "../onboard/form.js";
import { infoButton } from "../wall/info.js";
import { HOSTED, call, errorCode, failWords, spacePath, tenantApi } from "./api.js";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");
// "17 Oct, 14:02 UTC"; with the year for what goes into the record.
export function whenWords(iso, { year = false } = {}) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}${year ? ` ${d.getUTCFullYear()}` : ""}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}
const hhmm = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
};

export const ROLE_WORDS = { ops_manager: "Ops manager", dispatcher: "Dispatcher", viewer: "Viewer" };
// The airline's state as a shape and a word (design RATIONALE §3): never colour alone.
export const STATE_BADGE = {
  setup: ["sbadge--draft", "NOT STARTED"],
  shadow: ["sbadge--shadow", "SHADOW"],
  live: ["sbadge--live", "LIVE"],
  suspended: ["sbadge--suspended", "SUSPENDED"],
};
export const stateBadge = (state) => {
  const [cls, word] = STATE_BADGE[state] || ["sbadge--draft", String(state || "").toUpperCase()];
  return el("span", { class: `sbadge ${cls}` }, el("i", { "aria-hidden": "true" }), word);
};

export const WAITING_WORDS = "TEPHRA staff approve hosting after verification. This page says when.";
// The card's one line; what the space is sits behind its (i).
const LEAD = "TEPHRA on your flights, for the people you invite.";
const LEAD_MORE = "The same TEPHRA, in your own space on this site, with your policy and your assistant. No one else can sign in to it.";
const leadLine = () => el("p", { class: "golive__lead" }, ...infoTail(LEAD, { topic: "your space", label: "About your space", text: LEAD_MORE }));
const ITEM_LINK = { feeds: "Feeds", assistant: "Assistant", policy: "Policy", people: "People" };
// Contacting TEPHRA staff: the one channel the site names (privacy notice, "Questions").
export const CONTACT_HREF = "https://github.com/officialasishkumar/tephra-public/issues";

// Why Start shadow runs cannot run, in words, or null when it can. `region` is the one chosen in
// the select when the server could not derive it.
export function startBlock(golive, region = null) {
  if (!golive) return "Finish the checklist";
  const open = (golive.items || []).filter((i) => !i.done).length;
  switch (golive.blocked) {
    case null:
    case undefined:
      return golive.can_start ? null : "Finish the checklist";
    case "checklist": {
      // the first unmet blocker is reported; a full site is said too, so finishing the
      // checklist is not taken as enough to start
      const full = golive.slots && golive.slots.used >= golive.slots.max;
      return `Finish the checklist: ${open} of ${(golive.items || []).length} still open${full ? ". No airline place is free either" : ""}`;
    }
    case "region":
      return region ? null : "Choose a region";
    case "airline_limit_reached":
      return "All airline places on this site are in use. TEPHRA staff can see you are ready.";
    case "site_memory":
      return "This site's memory is full. TEPHRA staff can see you are ready.";
    default:
      return "Finish the checklist";
  }
}

export const slotWords = (slots) => `${slots.used} of ${slots.max} airline ${slots.max === 1 ? "place" : "places"} in use`;
export const isOpsManager = (header) => header?.you?.role === "ops_manager";

// The answer a change got, in words a person can act on.
export function changeWords(res, name) {
  const code = errorCode(res);
  const words = {
    checklist_open: "The checklist is not finished: reload to see what is open.",
    airline_limit_reached: "All airline places on this site are in use. TEPHRA staff can see you are ready.",
    site_memory: "This site's memory is full. TEPHRA staff can see you are ready.",
    wrong_state: "Someone changed this airline's state in another tab. Reload to see it.",
    confirm_icao: "Type the airline's code exactly, in capitals.",
    not_verified: "Your airline is not verified yet.",
    hosting_not_approved: WAITING_WORDS,
    icao_taken: `Another airline already has a space with this code. Contact TEPHRA staff.`,
    already_set_up: `${name || "Your airline"} is set up already. Reload to see it.`,
    tenant_suspended: "TEPHRA staff suspended this airline: nothing can be changed.",
    role: "Only an ops manager can do this.",
    name_taken: "Another member uses this name. Choose another.",
  }[code];
  return words || failWords(res);
}

function card(id, title, tag, ...kids) {
  return el("section", { id: "golive", class: "card wcard golive", "aria-labelledby": id },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-live")), el("h2", { id, text: title }), tag),
    ...kids);
}

function spaceLine(icao, name, { open }) {
  const address = `${location.host}${spacePath(icao, "/")}`;
  return el("div", { class: "space" }, icon("i-lock"), el("code", { text: address }),
    open
      ? el("a", { class: "link", href: spacePath(icao, "/") }, el("span", { text: `Open TEPHRA for ${name} ›` }))
      : el("span", { class: "hint", text: "Map · Desk · Feeds · Settings" }));
}

const inlineStatus = (id) => el("p", { id, class: "inline-alert", role: "status", hidden: true });
function say(line, words) {
  line.hidden = !words;
  line.replaceChildren(...(words ? [icon("st-caution"), el("span", { text: words })] : []));
}

// --- not set up yet: the record holder names themself once and the setup space is made ---------

export function setupCard(can, { onDone }) {
  const name = checkOnLeave(input({ autocomplete: "name", maxlength: 32 }), () => ruleMessage("member.name", name.value));
  const status = inlineStatus("gl-setup-status");
  const go = el("button", { type: "submit", class: "btn btn--primary btn--lg" }, el("span", { text: `Set up TEPHRA for ${can.name}` }), icon("i-arrow-right"));
  const form = el("form", { class: "authform golive__setup", novalidate: true },
    field({ id: "gl-name", label: "Your name on TEPHRA", rule: "2 to 32 characters", control: name,
      info: { topic: "your name", label: "About your name", text: "Your dispatchers see it on your decisions and in the airline's record." } }),
    status,
    el("div", { class: "golive__go" }, go, el("p", { text: "You become its first ops manager; nothing runs yet." })));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = ruleMessage("member.name", name.value);
    setError(name, bad);
    if (bad) {
      name.focus();
      return;
    }
    go.disabled = true;
    const res = await call(HOSTED.setup, { method: "POST", body: { display_name: name.value.trim().replace(/\s+/g, " ") } });
    go.disabled = false;
    if (res.ok) {
      onDone();
      return;
    }
    say(status, changeWords(res, can.name));
  });
  return card("gl-h", "Go live on TEPHRA", null, leadLine(), form);
}

// --- setup: the checklist, the region, the places, Start shadow runs ---------------------------

function checklist(items) {
  return el("ol", { class: "clist", "aria-label": "Before you start" }, ...items.map((item, i) => el("li", { class: item.done ? "is-done" : null },
    el("span", { class: "clist__n" }, item.done ? icon("i-check") : el("span", { "aria-hidden": "true", text: String(i + 1) }), el("span", { class: "sr-only", text: item.done ? "Done:" : "To do:" })),
    el("span", {}, el("b", { text: item.title }), el("span", { text: item.detail })),
    item.href ? el("a", { class: "link", href: item.href, text: ITEM_LINK[item.key] || "Open" }) : null)));
}

const modes = () => el("div", { class: "modes" },
  el("div", { class: "is-now" },
    el("span", { class: "stamp stamp--shadow" }, el("i", { "aria-hidden": "true" }), "SHADOW"),
    el("p", {}, el("b", { text: "First. " }), "Every draft says ", el("b", { text: "Shadow · not for use" }),
      el("span", { class: "tline__end" }, ".", infoButton({ topic: "shadow runs", label: "About shadow runs", text: "TEPHRA runs on your real flights, and your dispatchers decide its drafts at the Desk." })))),
  el("div", {},
    stateBadge("live"),
    el("p", {}, el("b", { text: "Then. " }),
      ...infoTail("Your ops manager switches, on the record.", { topic: "LIVE", label: "About LIVE", text: "The stamp goes; drafts are for your dispatchers to use. The switch is recorded with a name and a time." }))));

function regionBlock(golive, onPick) {
  const r = golive.region;
  if (r && r.derived) {
    return el("p", { class: "golive__regionline" }, el("b", { text: "Region: " }), r.name, el("span", { class: "tdim", text: " · from your network's airports" }));
  }
  const select = el("select", { class: "input select" },
    el("option", { value: "", text: "Choose a region" }),
    ...(golive.regions || []).map((x) => el("option", { value: x.key, text: x.name, selected: r && r.key === x.key ? true : null })));
  select.addEventListener("change", () => onPick(select.value || null));
  return el("div", { class: "golive__region" },
    field({ id: "gl-region", label: "Region to watch", control: select,
      info: { topic: "the region", label: "About the region", text: "Your network's airports fall in several regions or in none, so you choose." } }),
    golive.region_note ? el("div", { class: "note note--notbuilt", role: "note" }, icon("i-info"), el("p", {}, el("b", { text: "Not built. " }), golive.region_note)) : null);
}

export function setupStateCard(icao, header, golive, { onDone }) {
  const ops = isOpsManager(header);
  const done = golive.items.filter((i) => i.done).length;
  let region = golive.region?.key || null;
  const why = el("p", { id: "gl-why", class: "golive__why" });
  const status = inlineStatus("gl-start-status");
  const start = ops ? el("button", { type: "button", id: "gl-start", class: "btn btn--primary btn--lg", "aria-describedby": "gl-why" }, el("span", { text: "Start shadow runs" }), icon("i-arrow-right")) : null;
  const draw = () => {
    const block = startBlock(golive, region);
    if (start) {
      start.disabled = Boolean(block);
      why.replaceChildren(...(block ? [icon("st-caution"), el("span", { text: `${block}.`.replace(/\.\.$/, ".") })] : [el("span", { text: "Recorded with your name. You can stop at any time." })]));
      why.className = block ? "golive__why status status--caution" : "golive__why";
    } else {
      why.replaceChildren(el("span", { text: `${ROLE_WORDS[header?.you?.role] || "Your role"}: an ops manager of ${header.name} starts shadow runs.` }));
    }
  };
  if (start) {
    start.addEventListener("click", async () => {
      start.disabled = true;
      const res = await call(tenantApi(icao, "/start"), { method: "POST", body: { region } });
      if (res.ok) {
        onDone();
        return;
      }
      say(status, changeWords(res, header.name));
      draw();
    });
  }
  draw();
  const ready = done === golive.items.length;
  return card("gl-h", "Go live on TEPHRA",
    el("span", { class: `status ${ready ? "status--ok" : "status--quiet"}` }, icon(ready ? "st-ok" : "st-off"), el("span", { text: `${done} of ${golive.items.length} ready` })),
    leadLine(),
    spaceLine(icao, header.name, { open: false }),
    checklist(golive.items),
    regionBlock(golive, (v) => {
      region = v;
      draw();
    }),
    modes(),
    el("p", { class: "golive__slots" }, icon("i-gauge"), el("span", { text: slotWords(golive.slots) })),
    status,
    el("div", { class: "golive__go" }, start, why));
}

// --- shadow or live: since when and by whom; Switch to LIVE, Back to SHADOW, Stop ----------------

function alarmLines(header) {
  const out = [];
  if (header.paused) {
    const resumes = header.paused.resumes_at ? ` Resumes 00:00 Pacific (${hhmm(header.paused.resumes_at)} UTC).` : "";
    out.push(header.paused.scope === "site"
      ? `Paused: the shared site's free daily database allowance is used.${resumes}`
      : `Paused: ${header.name}'s share of the site's free daily database allowance is used.${resumes}`);
  }
  if (header.runtime?.problem) out.push(header.runtime.problem);
  return out.map((t) => el("p", { class: "status status--serious" }, icon("st-serious"), el("span", { text: t })));
}

export function sinceWords(header) {
  if (header.state === "live" && header.live) return `Live since ${whenWords(header.live.at)}, switched by ${header.live.by}.`;
  const by = header.started?.by ? `, started by ${header.started.by}` : "";
  return `Shadow runs since ${whenWords(header.state_since)}${by}.`;
}

export function runningCard(icao, header, { onDone }) {
  const ops = isOpsManager(header);
  const live = header.state === "live";
  const acts = ops ? el("div", { class: "golive__go" },
    live
      ? actionButton("gl-shadow", "Back to SHADOW…", "btn--secondary", () => reasonDialog(icao, header, "shadow", onDone))
      : actionButton("gl-live", "Switch to LIVE…", "btn--primary btn--lg", () => liveDialog(icao, header, onDone)),
    actionButton("gl-stop", live ? "Stop TEPHRA…" : "Stop shadow runs…", "btn--secondary", () => reasonDialog(icao, header, "stop", onDone))) : null;
  return card("gl-h", "On TEPHRA", stateBadge(header.state),
    el("p", { text: sinceWords(header) }),
    ...alarmLines(header),
    spaceLine(icao, header.name, { open: true }),
    acts);
}

function actionButton(id, words, cls, onClick) {
  const b = el("button", { type: "button", id, class: `btn ${cls}`, "aria-haspopup": "dialog" }, el("span", { text: words }));
  b.addEventListener("click", onClick);
  return b;
}

function dialogShell(headingId, ...kids) {
  const dlg = document.getElementById("ob-dlg");
  const form = el("form", { class: "pdlg__form", novalidate: true }, ...kids);
  dlg.replaceChildren(form);
  dlg.setAttribute("aria-labelledby", headingId);
  return { dlg, form };
}

const recordLine = (words) => el("div", { class: "dlg-rec" }, el("small", { text: "Goes into your record" }), el("span", { text: words }));

export function liveDialog(icao, header, onDone) {
  const name = header.name;
  const you = header.you || {};
  const attest = el("input", { type: "checkbox", id: "live-attest", "aria-describedby": "live-attest-err" });
  const typed = input({ autocomplete: "off", spellcheck: "false", autocapitalize: "characters", maxlength: 3 });
  const status = inlineStatus("live-status");
  const cancel = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  const go = el("button", { type: "submit", class: "btn btn--primary" }, el("span", { text: `Switch ${icao} to LIVE` }));
  const illustrative = String(header.policy?.label || "").startsWith("ILLUSTRATIVE");
  const { dlg, form } = dialogShell("live-h",
    el("h2", { id: "live-h", class: "h2", text: `Switch ${name} to LIVE?` }),
    el("p", { class: "body2" }, "Drafts stop saying ", el("b", { text: "Shadow · not for use" }), ", and your dispatchers may use the advisories they approve in your operation."),
    el("p", { class: "note" }, icon("i-hand"), el("span", {},
      ...infoTail("TEPHRA still sends nothing to an aircraft or to any system.", { topic: "approved advisories", label: "Where an approved advisory goes", text: "An approved advisory goes to your outbound list; a person passes it on." }))),
    illustrative
      ? el("p", { class: "note note--caution" }, icon("i-alert"),
        el("span", {}, `Ash policy v${header.policy.version} is `, el("b", { text: "ILLUSTRATIVE" }), ": its acceptance under your SRA is not recorded. ",
          el("span", { class: "tline__end" }, el("a", { class: "link", href: spacePath(icao, "/settings/policy"), text: "Record it ›" }),
            infoButton({ topic: "ILLUSTRATIVE", label: "About ILLUSTRATIVE", text: "Every draft says so until you record it in Settings › Policy." }))))
      : null,
    el("div", { class: "field" },
      el("label", { class: "check" }, attest, el("span", {}, el("b", { text: `I am ${name}'s ops manager` }), " and may put TEPHRA's drafts into our operation.")),
      el("p", { id: "live-attest-err", class: "err", hidden: true })),
    field({ id: "live-icao", label: `Type ${icao} to confirm`, control: typed }),
    recordLine(`Switched to LIVE by ${you.name || "you"} (${ROLE_WORDS[you.role] || "Ops manager"}), ${whenWords(new Date().toISOString(), { year: true })}.`),
    status,
    el("div", { class: "pdlg__acts" }, cancel, go));
  cancel.addEventListener("click", () => dlg.close());
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    setError(attest, attest.checked ? null : "Tick to continue");
    const typedBad = !typed.value.trim() ? "Required" : typed.value.trim() !== icao ? `Type ${icao}` : null;
    setError(typed, typedBad);
    if (!attest.checked || typedBad) {
      (attest.checked ? typed : attest).focus();
      return;
    }
    go.disabled = true;
    const res = await call(tenantApi(icao, "/live"), { method: "POST", body: { confirm_icao: typed.value.trim(), attest: true } });
    go.disabled = false;
    if (res.ok) {
      dlg.close();
      onDone();
      return;
    }
    say(status, changeWords(res, name));
  });
  dlg.showModal();
  attest.focus();
}

// Back to SHADOW (live -> shadow) and Stop (shadow or live -> setup) both need a reason.
export function reasonDialog(icao, header, kind, onDone) {
  const name = header.name;
  const you = header.you || {};
  const live = header.state === "live";
  const words = kind === "shadow"
    ? { h: `Put ${name} back to SHADOW?`, lead: "New drafts say Shadow · not for use again.", more: "What was approved in LIVE stays as it was.", go: "Back to SHADOW", rec: "Back to SHADOW", path: "/shadow" }
    : { h: live ? `Stop TEPHRA for ${name}?` : `Stop shadow runs for ${name}?`, lead: "Runs end and the airline place is freed.", more: "Your space goes back to setup. Your settings, people, keys and record are kept, and you can start again from here.", go: live ? "Stop TEPHRA" : "Stop shadow runs", rec: live ? "Stopped TEPHRA" : "Stopped shadow runs", path: "/stop" };
  const reason = checkOnLeave(el("textarea", { class: "input textarea", rows: "3", maxlength: 300 }), () => ruleMessage("policy.reason", reason.value));
  const status = inlineStatus("rs-status");
  const cancel = el("button", { type: "button", class: "btn btn--secondary", text: "Cancel" });
  const go = el("button", { type: "submit", class: kind === "stop" ? "btn btn--serious" : "btn btn--primary" }, el("span", { text: words.go }));
  const rec = el("span", { text: `${words.rec} by ${you.name || "you"}: …` });
  reason.addEventListener("input", () => {
    rec.textContent = `${words.rec} by ${you.name || "you"}: ${reason.value.trim() || "…"}`;
  });
  const { dlg, form } = dialogShell("rs-h",
    el("h2", { id: "rs-h", class: "h2", text: words.h }),
    el("p", { class: "body2" }, ...infoTail(words.lead, { topic: kind === "shadow" ? "back to SHADOW" : "stopping", label: kind === "shadow" ? "About going back to SHADOW" : "About stopping", text: words.more })),
    field({ id: "rs-reason", label: "Reason", rule: "3 to 300 characters", control: reason }),
    el("div", { class: "dlg-rec" }, el("small", { text: "Goes into your record" }), rec),
    status,
    el("div", { class: "pdlg__acts" }, cancel, go));
  cancel.addEventListener("click", () => dlg.close());
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = reason.value.trim();
    const bad = ruleMessage("policy.reason", reason.value);
    setError(reason, bad);
    if (bad) {
      reason.focus();
      return;
    }
    go.disabled = true;
    const res = await call(tenantApi(icao, words.path), { method: "POST", body: { reason: text } });
    go.disabled = false;
    if (res.ok) {
      dlg.close();
      onDone();
      return;
    }
    say(status, changeWords(res, name));
  });
  dlg.showModal();
  reason.focus();
}

// --- suspended by TEPHRA staff -----------------------------------------------------------

export function suspendedWords(header) {
  const s = header.suspended || {};
  const reason = String(s.reason || "no reason given").trim().replace(/[.\s]+$/, "");
  return {
    lead: `TEPHRA staff suspended ${header.name} on ${whenWords(s.at)}: ${reason}.`,
    rest: "Runs are stopped and pushes are refused.",
    more: `Your settings, people, keys and record are kept. TEPHRA staff can delete your data from ${whenWords(s.delete_after)}; nothing deletes it on its own.`,
  };
}

export function suspendedCard(icao, header) {
  const w = suspendedWords(header);
  return card("gl-h", "On TEPHRA", stateBadge("suspended"),
    el("div", { class: "banner", role: "status" }, icon("i-alert-serious"),
      el("div", { class: "golive__susp" }, el("b", { text: w.lead }),
        el("p", {}, ...infoTail(w.rest, { topic: "your data", label: "About your data", text: w.more })),
        el("a", { class: "btn btn--secondary btn--sm", href: CONTACT_HREF, rel: "noopener" }, el("span", { text: "Contact TEPHRA" }), icon("i-external-link")))),
    spaceLine(icao, header.name, { open: true }));
}

// --- the airlines a login belongs to ------------------------------------------------------------

export function airlinesList(memberships, { title = "Your airlines", id = "ya-h" } = {}) {
  return el("section", { id: "your-airlines", class: "card wcard", "aria-labelledby": id },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-dispatcher")), el("h2", { id, text: title })),
    el("ul", { class: "yairs" }, ...memberships.map((m) => el("li", {},
      el("span", { class: "ah-air__code", "aria-hidden": "true", text: m.icao }),
      el("span", { class: "yairs__who" }, el("b", { text: m.name }), el("small", { text: `${m.icao} · ${ROLE_WORDS[m.role] || m.role}` })),
      stateBadge(m.state),
      el("a", { class: "btn btn--secondary btn--sm", href: spacePath(m.icao, "/") }, el("span", { text: "Open" }), el("span", { class: "sr-only", text: ` ${m.name}` }), icon("i-arrow-right"))))));
}

// --- loading: what the overview needs for the hosted cards --------------------------------------

// { me, own, header, golive, error }: `own` is the login's membership of its own airline. A read
// that fails is kept as `error` and said where the card would be; nothing is drawn in its place.
export async function loadHosted(ownIcao) {
  const me = await call(HOSTED.me);
  if (me.status === 404) return null;   // hosting is off on this server
  if (!me.ok || !me.data) return { error: me };
  const own = (me.data.memberships || []).find((m) => m.icao === ownIcao) || null;
  if (!own) return { me: me.data, own: null };
  const [header, golive] = await Promise.all([
    call(tenantApi(own.icao, "/header")),
    own.state === "setup" ? call(tenantApi(own.icao, "/golive")) : Promise.resolve(null),
  ]);
  if (!header.ok || !header.data) return { me: me.data, own, error: header };
  if (golive && (!golive.ok || !golive.data)) return { me: me.data, own, error: golive };
  return { me: me.data, own, header: header.data, golive: golive ? golive.data : null };
}

// The cards for one verified airline's overview, in reading order.
export function hostedCards(view, hosted, { onChange }) {
  if (!hosted) return [];
  if (hosted.error) {
    return [el("p", { id: "golive", class: "status status--serious" }, icon("st-serious"), el("span", { text: `TEPHRA could not read your airline's hosting: ${failWords(hosted.error)}` }))];
  }
  const me = hosted.me;
  const out = [];
  const icao = view.answers?.airline?.icao;
  if (hosted.own && hosted.header) {
    const h = hosted.header;
    if (h.state === "setup" && hosted.golive) out.push(setupStateCard(icao, h, hosted.golive, { onDone: onChange }));
    else if (h.state === "shadow" || h.state === "live") out.push(runningCard(icao, h, { onDone: onChange }));
    else if (h.state === "suspended") out.push(suspendedCard(icao, h));
  } else if (me.can_set_up) {
    out.push(setupCard(me.can_set_up, { onDone: onChange }));
  }
  const others = (me.memberships || []).filter((m) => m.icao !== icao);
  if (others.length) out.push(airlinesList(others, { title: "Other airlines you belong to" }));
  return out;
}
