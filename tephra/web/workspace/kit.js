// The setup kit (SPEC-v2 §9): everything an airline needs to run its own TEPHRA on its own fleet,
// made in this browser from its stored answers. buildKit and envLines are pure (Node tests them);
// the card and the kit page below draw it. The site's only secret field, the Gemini API key, lives
// on the kit page alone: no `name`, outside any form, cleared on pagehide and after the download,
// so it reaches the zip made in this tab and nothing else.

import { el, icon } from "../wall/util.js";
import { makeZip } from "./zip.js";
import { PATHS, call, text } from "./api.js";
import { loadLocal, saveLocal } from "../onboard/draft.js";
import { DEFAULT_OLLAMA_URL, FREE_TIER_MODELS, inBox, isEditablePolicyValue, ruleMessage } from "../onboard/pages.js";

export const KIT_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789";
export const PLACEHOLDER = "<made when you download>";
const REPO = "https://github.com/officialasishkumar/tephra";
const REGION_KEYS = "java_bali | halmahera | kyushu";

// --- secrets ------------------------------------------------------------------------------------------

function pick(crypto, n) {
  const out = [];
  while (out.length < n) {
    const bytes = crypto.getRandomValues(new Uint8Array(n * 2));
    for (const b of bytes) {
      // 240 = 8 x 30: rejection sampling keeps every character equally likely
      if (b < 240 && out.length < n) out.push(KIT_ALPHABET[b % KIT_ALPHABET.length]);
    }
  }
  return out.join("");
}

const b64url = (bytes) => {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};

// The kit's own Desk PIN (12 characters from the recovery alphabet, about 59 bits) and two
// 32-byte secrets in base64url (43 characters).
export function makeSecrets(crypto) {
  const pin = pick(crypto, 12);
  return {
    pin: `${pin.slice(0, 4)}-${pin.slice(4, 8)}-${pin.slice(8, 12)}`,
    session_secret: b64url(crypto.getRandomValues(new Uint8Array(32))),
    task_token: b64url(crypto.getRandomValues(new Uint8Array(32))),
  };
}

// --- airline.env --------------------------------------------------------------------------------------

// The preset whose box holds the main base, or null (outside the three areas, or not in
// TEPHRA's airport list).
export function regionFor(code, positions, regions) {
  const at = positions?.[code];
  if (!at) return null;
  return (regions || []).find((r) => inBox(r.bbox, at))?.key || null;
}

const isoDay = (d) => d.toISOString().slice(0, 10);

// The lines of airline.env, in the order of SPEC-v2 §9.2. Lines whose answer is not given yet
// are left out (the onboarding aside shows the kit as it grows). extra: { date, origin,
// statusLabel, positions, regions, known (a Set of TEPHRA's airports), secrets, geminiKey, ollamaUrl }.
export function envLines(answers, extra = {}) {
  const a = answers?.airline || {};
  const s = extra.secrets || { pin: PLACEHOLDER, session_secret: PLACEHOLDER, task_token: PLACEHOLDER };
  const lines = [
    `# TEPHRA for ${a.name || "your airline"}${a.icao ? ` (${a.icao})` : ""}, made in the workspace on ${extra.date || isoDay(new Date())}.`,
  ];
  if (extra.statusLabel) lines.push(`# Status on ${extra.origin}: ${extra.statusLabel}.`);
  lines.push(
    "# Decision support only. Not for operational use without your safety risk assessment,",
    "# your regulator's acceptance and, with Gemini, Google's written agreement for that use.",
    "# Copy this file to .env in your TEPHRA folder. It holds secrets: never commit it.",
    "TEPHRA_MODE=LIVE",
    "TEPHRA_AUTO_REPLAY=false",
  );
  if (a.main_base && extra.positions && extra.regions) {
    const region = regionFor(a.main_base, extra.positions, extra.regions);
    if (region) lines.push(`TEPHRA_REGION=${region}`);
    else lines.push("# Your main base is outside TEPHRA's three areas; its live feeds cover only these:", `# TEPHRA_REGION=${REGION_KEYS}`);
  }
  lines.push(
    `TEPHRA_FEATURES=connect${answers?.feeds?.pilot_reports ? ",crew" : ""}`,
    "TEPHRA_VISITOR_ACCESS=off",
    "# Recovery re-planning for your network is not built.",
    "TEPHRA_RECOVERY_AUTO=false",
    "TEPHRA_VONA_LIVE=false",
    "TEPHRA_STORE=sqlite",
    "TEPHRA_LOCAL_SCHEDULER=true",
    `TEPHRA_DESK_PIN=${s.pin}`,
    `TEPHRA_SESSION_SECRET=${s.session_secret}`,
    `TEPHRA_TASK_TOKEN=${s.task_token}`,
  );
  const prefixes = [a.callsign_prefix, ...(answers?.fleet?.extra_prefixes || [])].filter(Boolean);
  if (prefixes.length) lines.push(`TEPHRA_FLEET_PREFIXES=${prefixes.join(",")}`);
  const hexes = (answers?.fleet?.aircraft || []).map((r) => r.hex).filter(Boolean);
  if (hexes.length) lines.push(`TEPHRA_FLEET_HEXES=${hexes.join(",")}`);
  if (extra.known) {
    const own = (answers?.network?.airports || []).map((x) => x.icao).filter((c) => extra.known.has(c));
    if (own.length) lines.push(`TEPHRA_NETWORK_AIRPORTS=${own.join(",")}`);
  }
  lines.push("TEPHRA_POLICY_FILE=policy/airline.json");
  // Who the drafts name: the airline itself, and each flight by its callsign, its flight in
  // flights.json or its registration (an own fleet needs the name and the ICAO to start).
  lines.push(
    ...(a.name ? [`TEPHRA_AIRLINE_NAME=${JSON.stringify(a.name)}`] : []),
    ...(a.icao ? [`TEPHRA_AIRLINE_ICAO=${a.icao}`] : []),
    ...(a.iata ? [`TEPHRA_AIRLINE_IATA=${a.iata}`] : []),
    "TEPHRA_AIRLINE_SCHEDULE=airline/flights.json",
    "TEPHRA_AIRLINE_FLEET=airline/fleet.json",
  );
  const m = answers?.assistant || {};
  if (m.provider) lines.push("# --- model ---");
  if (m.provider === "gemini") {
    lines.push(
      "TEPHRA_LLM=gemini",
      ...(extra.geminiKey ? [] : ["# Paste your own Google AI Studio key after the = (TEPHRA does not start until you do)."]),
      `GEMINI_API_KEY=${extra.geminiKey || ""}`,
      `TEPHRA_MODEL=${m.model}`,
      `TEPHRA_MODEL_LITE=${m.model_lite}`,
    );
    for (const id of new Set([m.model, m.model_lite])) {
      if (id && !FREE_TIER_MODELS.includes(id)) lines.push(`# ${id} has no row in TEPHRA's free-tier table: it is never called (AI UNAVAILABLE) until you add one with TEPHRA_MODEL_LIMITS (.env.example shows the shape).`);
    }
  } else if (m.provider === "ollama") {
    lines.push("TEPHRA_LLM=ollama", `TEPHRA_OLLAMA_URL=${extra.ollamaUrl || DEFAULT_OLLAMA_URL}`, `TEPHRA_MODEL=${m.model}`, `TEPHRA_MODEL_LITE=${m.model_lite}`);
  } else if (m.provider === "none") {
    lines.push("TEPHRA_LLM=stub  # NO MODEL: code checks only");
  }
  return lines;
}

// --- policy.json --------------------------------------------------------------------------------------

const UNIT_WORDS = { NM: "NM", ft: "ft", min: "min", m: "m", kt: "kt", deg: "degrees", FL: "FL", count: "", s: "s", USD: "USD" };
const sentence = (t) => (/[.!?]$/.test(t) ? t : `${t}.`);

// The active policy with the airline's changes, keeping its ILLUSTRATIVE label (the only label the
// schema allows: TEPHRA cannot check an SRA). Unchanged values stay byte for byte.
export function policyJson(policy, answers, now) {
  const out = JSON.parse(JSON.stringify(policy));
  const a = answers.airline;
  out.policy_id = `${a.icao}-POLICY-A`;
  out.version = `${now.getUTCFullYear()}.${now.getUTCMonth() + 1}.1`;
  out.preset = "A";
  out.title = `${a.name} operator policy A (from onboarding, ILLUSTRATIVE)`;
  out.sra_ref = answers.policy.sra_ref || null;
  out.risk_owner = answers.policy.risk_owner;
  for (const c of answers.policy.changes || []) {
    if (!isEditablePolicyValue(c.name)) continue;
    const [block, key] = c.name.split(".");
    const v = out[block]?.[key];
    if (!v) continue;
    const unit = UNIT_WORDS[v.unit] ?? v.unit;
    v.source = `Set by the operator: ${sentence(c.reason)} Policy A had ${v.value}${unit ? ` ${unit}` : ""}.`;
    v.value = c.value;
  }
  return out;
}

// --- CHECKLIST.md -------------------------------------------------------------------------------------

function modelStep(m, haveKey) {
  if (m.provider === "gemini") {
    return [
      haveKey ? "Your Google AI Studio key is in `.env`." : "Paste your own Google AI Studio key after `GEMINI_API_KEY=` in `.env`; TEPHRA does not start without it.",
      "When the assistant's free daily limit is spent it says AI UNAVAILABLE and plans nothing in its place.",
      "A model with no row in TEPHRA's free-tier table is never called until you add one with `TEPHRA_MODEL_LIMITS` (`.env.example` shows the shape).",
    ].join(" ");
  }
  if (m.provider === "ollama") return `Run \`ollama pull ${m.model}\`${m.model_lite !== m.model ? ` and \`ollama pull ${m.model_lite}\`` : ""}, then \`ollama serve\` at the address in \`.env\`.`;
  return "Nothing to do: TEPHRA runs its code checks with no model, labelled NO MODEL.";
}

export function checklist(answers, { date, icao, haveKey = false, haveSchedule = false }) {
  const a = answers.airline;
  const dir = `tephra-kit-${icao}`;
  const push = "python3 push.py --url http://localhost:8080 --key tph_...";
  const lines = [
    `# Run your own TEPHRA: ${a.name} (${a.icao})`,
    "",
    `Made in the workspace on ${date}. Decision support only: a person approves every advisory, and nothing is sent to an aircraft.`,
    "",
    `- [ ] **1. What this is.** A private TEPHRA for ${a.name}, which checks only your fleet and the aircraft you push. Each flight is named by your callsign, else the flight number of a flight plan you pushed that is flying now, else its flight in flights.json, else its registration. Not built: one shared service for many airlines; Policy B; recovery re-planning for your network; a sign-in for the map page.`,
    `- [ ] **2. Get TEPHRA.** Clone ${REPO}, then run \`uv sync\` in it (or build its Docker image).`,
    `- [ ] **3. Put the kit in place.** In the TEPHRA folder: \`cp ${dir}/airline.env .env\`, \`cp ${dir}/policy.json data/policy/airline.json\`, and \`mkdir -p data/airline && cp ${dir}/flights.json ${dir}/fleet.json data/airline/\`.`,
    `- [ ] **4. The model.** ${modelStep(answers.assistant, haveKey)}`,
    "- [ ] **5. Start it.** `uv run tephra`, then open http://localhost:8080/demo for the map and http://localhost:8080/desk for the Desk with your Desk PIN (in `.env`). The map page and its read API have no sign-in: keep TEPHRA on your own network or put your own access control in front of it.",
    "- [ ] **6. Make a push key.** Desk › account menu › Data connections › New connection. The key is shown once.",
    `- [ ] **7. Push your data.** ${haveSchedule ? `\`${push} plans --schedule flights.json --fleet fleet.json --date YYYY-MM-DD\`, then` : "Fill flights.json and crews.json (formats below) for flight plans; then"} \`${push} positions <your-export.csv>\` (each position with its \`observed_at\`), or add \`--stamp-now\` for a file written in the last minute. \`--dry-run\` prints the batches and sends nothing.`,
    "- [ ] **8. Check it.** `GET /api/fleet` shows your prefixes and aircraft count; only your fleet's flights become drafts. For Cloud Run instead, read `deploy/README.md` first: a billing account is needed even inside the free tier, and an always-on instance is billed while it runs.",
  ];
  if (!haveSchedule) {
    lines.push(
      "",
      "## The schedule formats",
      "",
      '`flights.json`: `{"header": {"label", "anchor_utc_offset_h"}, "flights": [{"flight_no", "origin", "dest", "std_min", "block_min", "tail"?, "pax_booked"?, "pair_id"?, "callsign"?, "days"?}]}`. `anchor_utc_offset_h` is your schedule\'s hours from UTC (-12 to 14); `std_min` is minutes after its midnight (0 to 2879); `block_min` is above 0; `days` holds weekdays as in SSIM (1 is Monday), absent means daily; a `tail` is one of your registrations.',
      "",
      '`crews.json`: `{"crews": [{"crew_id", "base", "report_min"}]}`, with `base` an ICAO airport code and `report_min` minutes after midnight (0 to 2879).',
    );
  }
  return `${lines.join("\n")}\n`;
}

// --- the kit ------------------------------------------------------------------------------------------

const json = (v) => `${JSON.stringify(v, null, 2)}\n`;

function scheduleFile(textIn) {
  try {
    return textIn ? json(JSON.parse(textIn)) : null;
  } catch {
    return null;
  }
}

// ctx: { airline: AirlineView, policy, positions, regions, known, now, origin, secrets,
//        geminiKey?, ollamaUrl?, files?: { flights, crews }, pushTool } -> [{ path, text }]
export function buildKit(ctx) {
  const view = ctx.airline;
  const answers = view.answers;
  const icao = answers.airline.icao.toLowerCase();
  const date = isoDay(ctx.now);
  const dir = `tephra-kit-${icao}`;
  const flights = scheduleFile(ctx.files?.flights);
  const crews = scheduleFile(ctx.files?.crews);
  const haveSchedule = Boolean(flights && crews);
  const env = envLines(answers, {
    date, origin: ctx.origin, statusLabel: view.status_label, positions: ctx.positions, regions: ctx.regions, known: ctx.known,
    secrets: ctx.secrets, geminiKey: answers.assistant.provider === "gemini" ? ctx.geminiKey || "" : "", ollamaUrl: ctx.ollamaUrl,
  });
  const tails = answers.fleet.aircraft.map((r) => ({
    tail: r.registration, type: r.type_icao, seats: r.seats,
    ...(r.home_base ? { home_base: r.home_base } : {}),
    ...(r.hex ? { hex: r.hex } : {}),
  }));
  return [
    { path: `${dir}/airline.env`, text: `${env.join("\n")}\n` },
    { path: `${dir}/policy.json`, text: json(policyJson(ctx.policy, answers, ctx.now)) },
    { path: `${dir}/fleet.json`, text: json({ tails }) },
    { path: `${dir}/flights.json`, text: haveSchedule ? flights : json({ header: { label: `${answers.airline.name} schedule (fill in)`, anchor_utc_offset_h: null }, flights: [] }) },
    { path: `${dir}/crews.json`, text: haveSchedule ? crews : json({ crews: [] }) },
    { path: `${dir}/network.json`, text: json({ airports: answers.network.airports.map((x) => ({ icao: x.icao, alternates: x.alternates })) }) },
    { path: `${dir}/answers.json`, text: json({ answers, airline_id: view.id, status: view.status, status_label: view.status_label, workspace: `${ctx.origin}/workspace` }) },
    { path: `${dir}/push.py`, text: ctx.pushTool },
    { path: `${dir}/CHECKLIST.md`, text: checklist(answers, { date, icao, haveKey: Boolean(ctx.geminiKey), haveSchedule }) },
  ];
}

// --- what the kit needs from the server ---------------------------------------------------------------

const featurePositions = (fc) => Object.fromEntries((fc?.features || []).map((f) => [f.properties?.icao, f.geometry?.coordinates]).filter(([k, c]) => k && Array.isArray(c)));

// The policy, the airport list, the region boxes and push.py; null when any of them cannot be
// read (the kit is then not made: nothing stands in for a missing part).
export async function kitInputs() {
  const [policy, airports, state, pushTool] = await Promise.all([call(PATHS.policy), call(PATHS.airports), call(PATHS.state), text(PATHS.pushTool)]);
  if (!policy.ok || !policy.data?.policy || !airports.ok || !state.ok || !Array.isArray(state.data?.regions) || !pushTool) return null;
  const positions = featurePositions(airports.data);
  return { policy: policy.data.policy, positions, known: new Set(Object.keys(positions)), regions: state.data.regions, pushTool };
}

function save(bytes, name) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
  const a = el("a", { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Builds and saves tephra-kit-<icao>.zip; the answer says what happened, in words.
export async function downloadKit(view, { geminiKey = "" } = {}) {
  const inputs = await kitInputs();
  if (!inputs) return { ok: false, text: "Can't make the kit: this site's policy, airport list or push.py could not be read. Try again." };
  const local = loadLocal();
  const now = new Date();
  const files = buildKit({
    airline: view, ...inputs, now, origin: location.origin, secrets: makeSecrets(window.crypto),
    geminiKey, ollamaUrl: local.ollama_url || DEFAULT_OLLAMA_URL, files: local.files,
  });
  const icao = view.answers.airline.icao.toLowerCase();
  save(makeZip(files, now), `tephra-kit-${icao}.zip`);
  return { ok: true, text: `Saved tephra-kit-${icao}.zip. Unzip it and follow CHECKLIST.md.` };
}

// --- the card (the overview and the kit page) ---------------------------------------------------------

const FILES = [
  { names: ["airline.env"], icon: "i-file", what: "fleet filter, model settings" },
  { names: ["policy.json"], icon: "i-file", chip: "ILLUSTRATIVE" },
  { names: ["fleet.json", "flights.json", "crews.json"], icon: "i-file", what: "from your answers" },
  { names: ["network.json"], icon: "i-route", what: "your airports and alternates" },
  { names: ["push.py"], icon: "i-code", what: "stamps observed_at when it sends" },
  { names: ["CHECKLIST.md"], icon: "i-check", what: "8 steps" },
];

const haveFiles = (local) => Boolean(local.files?.flights && local.files?.crews);

// The Setup kit card. `keyField` (the kit page only) is the Gemini key input.
export function kitCard(view, { keyField = null, extra = null } = {}) {
  const local = loadLocal();
  const status = el("p", { class: "ws-status", role: "status" });
  const go = el("button", { type: "button", class: "btn btn--primary" }, icon("i-file"), el("span", { text: "Download setup kit (.zip)" }));
  go.addEventListener("click", async () => {
    go.disabled = true;
    go.lastChild.textContent = "Making the kit…";
    const res = await downloadKit(view, { geminiKey: keyField ? keyField.value.trim() : "" });
    if (keyField && res.ok) keyField.value = "";
    go.disabled = false;
    go.lastChild.textContent = "Download setup kit (.zip)";
    status.textContent = res.text;
    status.classList.toggle("ws-status--bad", !res.ok);
  });
  const gemini = view.answers.assistant.provider === "gemini";
  return el("section", { class: "card wcard wcard--wide", "aria-labelledby": "kit-h" },
    el("div", { class: "wcard__h" },
      el("span", { class: "wcard__ic" }, icon("i-file")),
      el("h2", { id: "kit-h", text: "Setup kit" }),
      el("span", { class: "chip", text: "made in your browser" })),
    el("p", { text: "Everything to run your own TEPHRA today, for your fleet only. Unzip it, follow CHECKLIST.md, then start TEPHRA with airline.env." }),
    el("ul", { class: "files" }, ...FILES.map((f) => el("li", {},
      icon(f.icon),
      el("span", { class: "files__names" }, ...f.names.flatMap((n, i) => [i ? el("span", { class: "files__sep", "aria-hidden": "true", text: " · " }) : null, el("code", { text: n })])),
      f.chip ? el("span", { class: "chip chip--illus", text: f.chip }) : el("span", { class: "files__what", text: f.what })))),
    el("p", { class: "body2", text: haveFiles(local) ? "Your schedule files are in this browser and go into the kit." : "Your schedule files are not in this browser: the kit holds empty flights.json and crews.json to fill." }),
    gemini && !keyField ? el("p", { class: "body2" }, "Add your Gemini key on the ", el("a", { class: "link", href: "/workspace/kit", text: "Setup kit page" }), ", or paste it into airline.env later.") : null,
    extra,
    el("div", { class: "wcard__foot" }, go),
    status);
}

// --- the kit page -------------------------------------------------------------------------------------

function keyInput() {
  const input = el("input", {
    id: "kit-gemini-key", class: "input mono", type: "password", autocomplete: "off", spellcheck: "false",
    autocapitalize: "off", "aria-describedby": "kit-gemini-hint",
  });
  window.addEventListener("pagehide", () => {
    input.value = "";
  });
  return input;
}

function ollamaField() {
  const local = loadLocal();
  const input = el("input", { id: "kit-ollama", class: "input mono", type: "url", autocomplete: "off", spellcheck: "false", value: local.ollama_url || DEFAULT_OLLAMA_URL, "aria-describedby": "kit-ollama-hint kit-ollama-err" });
  const err = el("p", { id: "kit-ollama-err", class: "err", hidden: true });
  input.addEventListener("change", () => {
    const msg = ruleMessage("assistant.ollama_url", input.value);
    err.hidden = !msg;
    err.replaceChildren(...(msg ? [icon("i-alert"), el("span", { text: msg })] : []));
    input.setAttribute("aria-invalid", msg ? "true" : "false");
    if (!msg) saveLocal({ ...loadLocal(), ollama_url: input.value.trim() });
  });
  return el("div", { class: "field" },
    el("label", { for: "kit-ollama", text: "Ollama address" }),
    input,
    el("p", { id: "kit-ollama-hint", class: "hint", text: local.ollama_url ? "Stays in this browser and goes only into your kit." : "TEPHRA's default. Stays in this browser and goes only into your kit." }),
    err);
}

// What goes into each file, as the download will write it (secrets shown as placeholders).
function previews(view, inputs) {
  const local = loadLocal();
  const files = buildKit({
    airline: view, ...inputs, now: new Date(), origin: location.origin,
    secrets: { pin: PLACEHOLDER, session_secret: PLACEHOLDER, task_token: PLACEHOLDER },
    geminiKey: "", ollamaUrl: local.ollama_url || DEFAULT_OLLAMA_URL, files: local.files,
  });
  return el("section", { class: "card wcard wcard--wide", "aria-labelledby": "kit-files-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic" }, icon("i-list")), el("h2", { id: "kit-files-h", text: "What goes into each file" })),
    el("div", { class: "kitfiles" }, ...files.map((f) => el("details", { class: "kitfile" },
      el("summary", {}, el("code", { text: f.path.split("/").pop() }), icon("i-chevron-down", "icon kitfile__chev")),
      el("pre", { class: "code", tabindex: "0", text: f.text })))));
}

export async function renderKitPage(main, view) {
  const provider = view.answers.assistant.provider;
  let keyField = null;
  let extra = null;
  if (provider === "gemini") {
    keyField = keyInput();
    extra = el("div", { class: "field" },
      el("label", { for: "kit-gemini-key" }, "Gemini API key ", el("span", { class: "opt", text: "(optional)" })),
      keyField,
      el("p", { id: "kit-gemini-hint", class: "hint", text: "It goes only into the zip made in this tab. TEPHRA never receives or stores it." }));
  } else if (provider === "ollama") {
    extra = ollamaField();
  }
  const loading = el("p", { class: "body2", text: "Loading what goes into each file…" });
  main.append(kitCard(view, { keyField, extra }), loading);
  const inputs = await kitInputs();
  loading.replaceWith(inputs ? previews(view, inputs) : el("p", { class: "body2", role: "status", text: "Can't show the files: this site's policy, airport list or push.py could not be read. Reload to try again." }));
}

