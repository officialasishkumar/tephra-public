// Settings › Assistant (SPEC-FINAL 5.6, mockup a-settings-assistant.html): the model the airline's
// drafts are written with, its own Google AI Studio key, and how today's calls are spent, from
// GET /api/tenant/assistant (AssistantTab). This tab is the airline's assistant home, so model
// ids, daily limits and lanes are said here and nowhere else in the space. The key is write-only:
// after saving it is shown as ••••last4, never again. No key, an unreadable key or no model gives
// AI UNAVAILABLE on every model step; nothing stands in for it. Every string goes in through el().

import { el, icon } from "../wall/util.js";
import { api } from "../base.js";
import { personName, whenWords, hhmmZ, reloadTenantHeader } from "../tenant-nav.js";
import { segmented } from "../onboard/form.js";
import { can, call, errorWords, pageHead, loadingCard, failCard, openDialog, inlineStatus, notBuiltNote, announce, refocus } from "../hosted.js";

export const TITLE = "TEPHRA Assistant";
export const LEAD = "The model your drafts are written with, your key, and how today's calls are spent.";
export const UNPAID = "Unpaid-tier data use: Google may use what TEPHRA sends with a free-tier key.";
export const KEY_WORDS = "Stored encrypted; never shown again or written to a log.";
export const FREE_LIMIT_WORDS = "the free-tier limit for this model";
export const LIMIT_HINT = "Set it to your key's own limit. TEPHRA stops before it, never after.";
const ms = (iso) => (iso ? Date.parse(iso) : NaN);
const pct = (n, of) => (of > 0 ? Math.max(0, Math.min(100, (n / of) * 100)) : 0);
const LANES = [
  { lane: "urgent", cls: "urgent", name: "Urgent", sub: "a flight or a plume read waits" },
  { lane: "interactive", cls: "desk", name: "Desk", sub: "a person waits" },
  { lane: "routine", cls: "routine", name: "Routine", sub: "paced through the day" },
];

export function stateLine(a) {
  if (a.state === "on") return el("p", { class: "astate", dataset: { tone: "on" } }, el("b", { text: "ON" }), el("span", { text: "TEPHRA Assistant writes your drafts with your key." }));
  if (a.state === "paused") return el("p", { class: "astate", dataset: { tone: "paused" } }, el("b", { text: "PAUSED" }), el("span", { text: a.reason ? `${a.reason}.` : "Today's calls on your key are used." }), el("span", { text: "Code checks still run; drafts that need the assistant say what is missing at the Desk." }));
  return el("p", { class: "astate", dataset: { tone: "unavailable" } }, el("b", { text: `AI UNAVAILABLE: ${a.reason || "no reason given"}` }), el("span", { text: "Every model step says so; nothing is put in its place." }));
}

export const limitOf = (a, model) => {
  const free = (a.models || []).find((m) => m.name === model)?.free_rpd ?? null;
  const set = a.daily_limits?.[model];
  return { limit: set ?? free, free, isFree: set == null || set === free };
};

export function keyBlock(a, { editable, onReplace, onRemove }) {
  const k = a.key || {};
  if (!k.set) return null;
  const replace = el("button", { type: "button", class: "btn btn--quiet btn--sm", text: "Replace…" });
  const remove = el("button", { type: "button", class: "btn btn--quiet btn--sm", text: "Remove…" });
  replace.addEventListener("click", onReplace);
  remove.addEventListener("click", onRemove);
  return el("div", { class: `secret${k.readable ? "" : " secret--bad"}` },
    icon("i-lock"),
    el("code", { "aria-label": `Model key ending ${k.last4}`, text: `••••${k.last4}` }),
    el("span", { class: "secret__who", text: k.readable
      ? `Added by ${personName(k.set_by?.by)}, ${whenWords(ms(k.set_by?.at))}. ${KEY_WORDS}`
      : "TEPHRA cannot read this key any more (its secret changed). Enter the key again: re-sealing an old key is not built." }),
    editable ? [replace, remove] : null);
}

export function keyForm({ onSave, first }) {
  const id = "akey";
  const input = el("input", { id, class: "input mono", type: "password", autocomplete: "off", spellcheck: "false", "aria-describedby": `${id}-hint` });
  const save = el("button", { type: "button", class: "btn btn--primary", text: first ? "Save the key" : "Save the new key" });
  const status = inlineStatus(`${id}-status`);
  save.addEventListener("click", () => onSave(input, status, save));
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); onSave(input, status, save); } });
  return el("div", { class: "field" },
    el("label", { for: id, text: "Your Google AI Studio key" }),
    el("div", { class: "keyform" }, input, save),
    el("p", { id: `${id}-hint`, class: "hint", text: `Write-only. ${KEY_WORDS}` }),
    status);
}

export function modelCard(a, h, handlers) {
  const editable = can(h, "ops_manager");
  const change = el("button", { type: "button", class: "btn btn--secondary btn--sm", text: "Change…" });
  change.addEventListener("click", handlers.change);
  const lim = (m) => {
    const l = limitOf(a, m);
    return l.limit == null ? "no daily limit known" : `${Number(l.limit).toLocaleString("en")} calls a day${l.isFree ? ` · ${FREE_LIMIT_WORDS}` : " · the limit you set for your key"}`;
  };
  const reserve = Math.round(Number(a.reserve_share || 0) * 100);
  return el("section", { class: "card wcard", "aria-labelledby": "mod-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-model")), el("h2", { id: "mod-h", text: "Model" }), editable ? change : null),
    stateLine(a),
    el("dl", { class: "kv" },
      el("dt", { text: "Provider" }), el("dd", { text: "Google AI Studio, your own key" }),
      el("dt", { text: "Reads plumes" }), el("dd", {}, a.model ? [el("span", { class: "mono", text: a.model }), el("small", { class: "limits tdim", text: lim(a.model) })] : "No model chosen"),
      el("dt", { text: "Plans and drafts" }), el("dd", {}, a.model_lite ? [el("span", { class: "mono", text: a.model_lite }), el("small", { class: "limits tdim", text: lim(a.model_lite) })] : "No model chosen"),
      el("dt", { text: "Held for the Desk" }), el("dd", { text: `${reserve} % of each model's calls` })),
    keyBlock(a, { editable, onReplace: handlers.replace, onRemove: handlers.remove }),
    !a.key?.set ? (editable ? keyForm({ onSave: handlers.saveKey, first: true }) : el("p", { class: "body2", text: "No model key is set. An ops manager adds it here." })) : null,
    el("p", { class: "hint", text: UNPAID }),
    notBuiltNote("Ollama on hosted TEPHRA: it runs only in your own TEPHRA."));
}

// The budget meter: per model, the stacked bar and three lanes; the Desk's share drawn apart as
// "Held for the Desk" with what is left. The 01:00 UTC release is said once, under the lanes.
export function budgetView(model, a) {
  const by = Object.fromEntries((model.lanes || []).map((l) => [l.lane, l]));
  const total = Number(model.limit || 0);
  const desk = by.interactive;
  const bar = el("div", { class: "budget__bar", role: "img", "aria-label": `${LANES.map((x) => `${x.name} ${by[x.lane]?.used ?? 0}`).join(", ")} of ${total} used` },
    ...LANES.map((x) => {
      const i = el("i", { class: `b-${x.cls}` });
      i.style.setProperty("width", `${pct(by[x.lane]?.used ?? 0, total).toFixed(1)}%`);
      return i;
    }));
  const own = a.daily_limits?.[model.model_id] != null;
  return el("div", { class: "budget" },
    el("p", { class: "body2" }, el("b", { text: `${model.used} of ${total}` }), ` calls on ${model.model_id}. ${total} is ${own ? "the daily limit you set for your key" : "TEPHRA's budget within the free-tier limit for this model"}.`),
    bar,
    desk ? el("div", { class: "reserve" },
      el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-dispatcher")),
      el("p", {}, el("b", { text: "Held for the Desk." }), " Ask, messages, handover and documents a dispatcher waits on. Routine work cannot take it."),
      el("p", { class: "reserve__n" }, el("b", { text: String(Math.max(0, desk.share - desk.used)) }), el("small", { text: `of ${desk.share} left` }))) : null,
    ...LANES.filter((x) => by[x.lane]).map((x) => {
      const l = by[x.lane];
      const i = el("i");
      i.style.setProperty("width", `${pct(l.used, l.share).toFixed(1)}%`);
      return el("div", { class: `lane lane--${x.cls}` },
        el("span", {}, el("b", { text: x.name }), el("small", { text: x.sub })),
        el("span", { class: "lane__bar", "aria-hidden": "true" }, i),
        el("span", { class: "lane__n", text: `${l.used} / ${l.share}` }));
    }),
    model.closed ? el("p", { class: "status status--caution" }, icon("st-caution"), el("span", { text: "Google closed this model's free quota for today." })) : null);
}

export function budgetCard(a, h, state = { model: null }) {
  const b = a.budget;
  const card = el("section", { class: "card wcard", "aria-labelledby": "b-h" });
  if (!b) {
    card.append(el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-gauge")), el("h2", { id: "b-h", text: "Today's calls" })),
      el("p", { text: `Today's calls show once TEPHRA runs for ${h.name}.` }));
    return card;
  }
  const models = b.models || [];
  const pick = state.model && models.some((m) => m.model_id === state.model) ? state.model : models[0]?.model_id;
  const panel = el("div", { id: "bm-panel", role: "tabpanel", "aria-labelledby": `bm-${pick}` });
  const draw = (key) => {
    const m = models.find((x) => x.model_id === key);
    panel.replaceChildren(m ? budgetView(m, a) : el("p", { text: "No model." }));
  };
  const tabs = el("div", {});
  const drawTabs = (key) => tabs.replaceChildren(segmented({
    label: "Model", idBase: "bm", value: key,
    tabs: models.map((m) => ({ key: m.model_id, text: m.model_id })),
    onChange: (k) => { state.model = k; drawTabs(k); draw(k); panel.setAttribute("aria-labelledby", `bm-${k}`); },
  }));
  drawTabs(pick);
  draw(pick);
  card.append(...[
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic", "aria-hidden": "true" }, icon("i-gauge")), el("h2", { id: "b-h", text: "Today's calls" }),
      el("span", { class: "tdim", text: `quota day ends ${hhmmZ(ms(b.resets_at)).replace("Z", " UTC")} (midnight Pacific)` })),
    models.length > 1 ? tabs : null, panel,
    el("p", { class: "hint", text: "Routine work starts only in step with the part of the day gone by. From 01:00 UTC, unused urgent and Desk calls flow to routine work." })].filter(Boolean));
  return card;
}

// ------------------------------------------------------------------ the page

export function render(h, a, handlers = {}) {
  return [pageHead(TITLE, LEAD), modelCard(a, h, handlers), budgetCard(a, h)].filter(Boolean);
}

export async function mount(host, h) {
  host.replaceChildren(pageHead(TITLE, LEAD), loadingCard("The assistant"));
  const res = await call(api("/tenant/assistant"));
  if (!res.ok || !res.data) {
    host.replaceChildren(pageHead(TITLE, LEAD), failCard(res, h, { title: "The assistant's settings did not load" }));
    return;
  }
  draw(host, h, res.data);
}

function draw(host, h, a) {
  const again = (data) => { draw(host, h, data); refocus(host, "#mod-h"); reloadTenantHeader(); };
  const saveKey = async (input, status, btn) => {
    const key = input.value.trim();
    if (!/^[A-Za-z0-9_-]{30,100}$/.test(key)) { status.say("That is not a Google AI Studio key: 30 to 100 letters, digits, - or _."); input.focus(); return; }
    btn.disabled = true;
    const res = await call(api("/tenant/assistant/key"), { method: "PUT", body: { key } });
    btn.disabled = false;
    input.value = "";
    if (res.ok && res.data) { announce("Key saved. It is not shown again."); again(res.data); return; }
    status.say(res.data?.error === "key_format" ? "That is not a Google AI Studio key: 30 to 100 letters, digits, - or _." : errorWords(res, h));
  };
  host.replaceChildren(...render(h, a, {
    change: () => changeDialog(h, a, again),
    replace: () => replaceDialog(h, again),
    remove: () => removeDialog(h, again),
    saveKey,
  }));
}

function replaceDialog(h, again) {
  const input = el("input", { id: "akey2", class: "input mono", type: "password", autocomplete: "off", spellcheck: "false" });
  openDialog({
    id: "akr", title: "Replace the model key?", goText: "Save the new key",
    body: [el("p", { class: "body2", text: `The old key is dropped at once. ${KEY_WORDS}` }), el("div", { class: "field" }, el("label", { for: "akey2", text: "The new key" }), input)],
    go: async (status) => {
      const key = input.value.trim();
      if (!/^[A-Za-z0-9_-]{30,100}$/.test(key)) { status.say("That is not a Google AI Studio key: 30 to 100 letters, digits, - or _."); input.focus(); return false; }
      const res = await call(api("/tenant/assistant/key"), { method: "PUT", body: { key } });
      input.value = "";
      if (res.ok && res.data) { again(res.data); announce("Key replaced. It is not shown again."); return true; }
      status.say(res.data?.error === "key_format" ? "That is not a Google AI Studio key." : errorWords(res, h));
      return false;
    },
  });
}

function removeDialog(h, again) {
  openDialog({
    id: "akd", title: "Remove the model key?", goText: "Remove the key", tone: "serious",
    body: [el("p", { class: "body2", text: "Without a key every model step says AI UNAVAILABLE: no model key is set. Code checks still run." })],
    go: async (status) => {
      const res = await call(api("/tenant/assistant/key"), { method: "DELETE" });
      if (res.ok && res.data) { again(res.data); announce("Key removed."); return true; }
      status.say(errorWords(res, h));
      return false;
    },
  });
}

// Model, lite model (the free-tier table only), the Desk's reserve and each model's daily limit,
// pre-set to the free-tier limit and never above it.
function changeDialog(h, a, again) {
  const models = a.models || [];
  const select = (id, value) => el("select", { id, class: "select" }, ...models.map((m) => el("option", { value: m.name, selected: m.name === value ? true : null, text: m.name })));
  const main = select("am-main", a.model);
  const lite = select("am-lite", a.model_lite);
  const reserve = el("input", { id: "am-res", class: "input mono", type: "number", min: "10", max: "50", step: "5", value: String(Math.round(Number(a.reserve_share || 0.2) * 100)) });
  const limits = el("div", { class: "pchg" });
  const inputs = new Map();
  const drawLimits = () => {
    const names = [...new Set([main.value, lite.value])];
    limits.replaceChildren(...names.map((name) => {
      const free = models.find((m) => m.name === name)?.free_rpd;
      const id = `am-lim-${name.replace(/[^a-z0-9]+/gi, "-")}`;
      const keep = inputs.get(name);
      const input = keep || el("input", { id, class: "input mono", type: "number", min: "1", max: String(free), step: "1", value: String(a.daily_limits?.[name] ?? free) });
      inputs.set(name, input);
      return el("div", { class: "pchg__row" }, el("div", { class: "pchg__top" },
        el("label", { for: id }, "Daily limit on your key", el("small", { text: `${name} · at most ${Number(free).toLocaleString("en")}, ${FREE_LIMIT_WORDS}` })), input));
    }));
  };
  main.addEventListener("change", drawLimits);
  lite.addEventListener("change", drawLimits);
  drawLimits();
  const { dlg } = openDialog({
    id: "amc", title: "Change the model", goText: "Save",
    body: [
      el("div", { class: "field" }, el("label", { for: "am-main", text: "Reads plumes" }), main),
      el("div", { class: "field" }, el("label", { for: "am-lite", text: "Plans and drafts" }), lite),
      el("p", { class: "hint", text: "Only models with a free tier on Google AI Studio are offered." }),
      limits,
      el("p", { class: "hint", text: LIMIT_HINT }),
      el("div", { class: "field" }, el("label", { for: "am-res", text: "Held for the Desk (%)" }), reserve, el("p", { class: "hint", text: "10 to 50 % of each model's calls, kept for what a dispatcher waits on." })),
    ],
    go: async (status) => {
      const share = Number(reserve.value);
      if (!Number.isFinite(share) || share < 10 || share > 50) { status.say("Held for the Desk: 10 to 50 %."); reserve.focus(); return false; }
      const daily = {};
      for (const name of new Set([main.value, lite.value])) {
        const input = inputs.get(name);
        const n = Number(input.value);
        const free = models.find((m) => m.name === name)?.free_rpd;
        if (!Number.isInteger(n) || n < 1 || (free != null && n > free)) { status.say(`${name}: a whole number from 1 to ${free}.`); input.focus(); return false; }
        if (n !== free) daily[name] = n;
      }
      const res = await call(api("/tenant/assistant"), { method: "PUT", body: { model: main.value, model_lite: lite.value, reserve_share: share / 100, daily_limits: daily } });
      if (res.ok && res.data) { again(res.data); announce("Model settings saved."); return true; }
      status.say(errorWords(res, h));
      return false;
    },
  });
  dlg.classList.add("pdlg--wide");
}
