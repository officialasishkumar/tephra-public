// The nine onboarding pages without the DOM: their names and copy, the rules each answer must
// meet (the same rules and words as tephra.airline.models.AirlineAnswers, so the browser and the
// server refuse the same things), the draft <-> AirlineAnswers mapping, where a draft resumes, the
// one-line summaries the Review and the workspace show, and the readers for the fleet and schedule
// files (read in the browser; nothing is uploaded). Pure: Node runs it in tests/test_onboard_js.py.

export const ONBOARD_FORMAT = "tephra.onboard/2";

// `name` is the page's full name (its title, the Review rows' aria); `short` is what the step
// list, the Next button and the Review rows show; `why` is the one line under the h1, and `info`
// what its (i) holds.
export const PAGES = [
  { key: "airline", n: 1, name: "Airline", short: "Airline", h1: "Your airline", why: "A TEPHRA dispatcher verifies your airline before anything runs." },
  { key: "policy", n: 2, name: "Ash policy", short: "Ash policy", h1: "Your ash policy", why: "Your margins around official ash areas.", info: "Under ICAO Doc 9974 each operator decides how it flies near ash, through its own safety risk assessment (SRA)." },
  { key: "fleet", n: 3, name: "Fleet", short: "Fleet", h1: "Your fleet", why: "Only these aircraft are checked." },
  { key: "network", n: 4, name: "Network", short: "Network", h1: "Your network", why: "Airports to watch for ash closure." },
  { key: "schedule", n: 5, name: "Schedule and crews", short: "Schedule", h1: "Your schedule and crews", why: "One day's flights and crews. Optional." },
  { key: "feeds", n: 6, name: "Data feeds", short: "Data feeds", h1: "Your data feeds", why: "Add what only you have.", info: "TEPHRA reads the public ash feeds and ADS-B by itself." },
  { key: "people", n: 7, name: "People", short: "People", h1: "Your people", why: "Who approves advisories." },
  { key: "assistant", n: 8, name: "Assistant (AI model)", short: "AI model", h1: "AI model", why: "Choose where it runs.", info: "TEPHRA Assistant reads the ash, plans each flight and drafts." },
  { key: "review", n: 9, name: "Review", short: "Review", h1: "Review and submit", why: "Check each page, then submit." },
];
export const PAGE_KEYS = PAGES.map((p) => p.key);
export const ANSWER_PAGES = PAGE_KEYS.slice(0, 8);
export const pageOf = (key) => PAGES.find((p) => p.key === key) || null;

// "What you will provide": one line per page on the landing, in a closed fold. README.md and
// docs/ONBOARDING.md keep the long wording.
export const PROVIDE = [
  { key: "airline", icon: "i-clipboard", name: "Airline", text: "Name, codes, base, ops contact" },
  { key: "policy", icon: "i-gauge", name: "Ash policy", text: "Policy A (ILLUSTRATIVE), your margins and reasons" },
  { key: "fleet", icon: "i-aircraft", name: "Fleet", text: "Registration, type, seats, ICAO 24-bit address" },
  { key: "network", icon: "i-route", name: "Network", text: "Airports you fly to, and alternates" },
  { key: "schedule", icon: "i-clock", name: "Schedule", text: "One day's flights and crews (optional)" },
  { key: "feeds", icon: "i-network", name: "Data feeds", text: "Positions, flight plans, pilot reports: ", code: "tephra.airline/1" },
  { key: "people", icon: "i-dispatcher", name: "People", text: "Dispatchers and their roles" },
  { key: "assistant", icon: "ta-16", name: "AI model", text: "Gemini, Ollama or none" },
  { key: "review", icon: "i-check", name: "Review", text: "Check and submit" },
];

// Who reads an airline's answers: the (i) behind "Private to your airline" on the sign-up card and the
// workspace header.
export const WHO_READS = "Only you and this site's TEPHRA dispatchers, who verify your airline, read your answers. Nothing you enter appears on the demo's map or the Desk's picture.";

// The one line the landing and the workspace say while this site runs no airline's operation.
export const NOT_ON_YET = "Running your airline on this site is not switched on yet.";
// The workspace's line once this site hosts airlines (SPEC hosted §9), with the site's own limit
// (TEPHRA_HOSTED_MAX_TENANTS, from GET /api/hosted/me).
export const notBuiltHosted = (max) => `TEPHRA runs at most ${max} ${max === 1 ? "airline" : "airlines"} at once on this site.`;

// TEPHRA's free-tier table (tephra/config.py DEFAULT_MODEL_LIMITS); a test keeps the two equal.
export const FREE_TIER_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash-lite-tts", "gemma-4-31b-it", "gemma-4-26b-a4b-it"];
export const DEFAULT_MODELS = { gemini: ["gemini-3.8-flash", "gemini-3.5-flash-lite"], ollama: ["gemma4:e4b", "gemma4:e4b"] };

// tephra/models.py POSITIVE_POLICY_VALUES: a zero would switch the check off (a test keeps them equal).
export const POSITIVE_POLICY_VALUES = [
  "alternates.min_ceiling_ft", "alternates.min_runway_m", "alternates.min_visibility_m", "alternates.search_radius_nm",
  "alternates.taf_eta_window_min", "alternates.terminal_radius_nm", "crew_reports.downwind_stretch_min", "crew_reports.level_margin_ft",
  "crew_reports.radius_nm", "crew_reports.valid_min", "drafts.position_lost_retire_min", "drafts.unexposed_retire_min", "fuel.hold_min",
  "planner.divert_within_min", "planner.hold_within_min", "planner.level_band_fl", "planner.level_search_ft", "planner.max_change_level_fl",
];
// The four values the Ash policy page shows first; the other editable ones sit under "More values".
export const KEY_POLICY_VALUES = [
  ["exposure.vertical_margin_ft", "Vertical margin"],
  ["reroute.buffer_nm", "Reroute buffer"],
  ["planner.hold_within_min", "Hold if entry within"],
  ["planner.divert_within_min", "Divert if entry within"],
];
// tephra.airline.policy_check.EDITABLE: every value outside recovery, plus the closure radius
// (recovery re-planning for an airline's network is not built, so its values stay as they are).
export const isEditablePolicyValue = (name) => !name.startsWith("recovery.") || name === "recovery.airport_closure_radius_nm";

export const EMAIL = /^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$/;
const ICAO4 = /^[A-Z]{4}$/;
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/;
const AI_STUDIO_MODEL = /^(gemini|gemma)-[a-z0-9.-]{1,60}$/;
const OLLAMA_TAG = /^[a-z0-9._-]{1,60}:[a-z0-9._-]{1,40}$/;

const str = (v) => (typeof v === "string" ? v.trim() : v == null ? "" : String(v).trim());
export const upper = (v) => str(v).toUpperCase();
export const hexOf = (v) => str(v).replace(/\s+/g, "").toLowerCase();
const orNull = (v) => (str(v) ? str(v) : null);
const lowerFirst = (t) => t.charAt(0).toLowerCase() + t.slice(1);
const count = (n, one, many = `${one}s`) => `${n.toLocaleString("en")} ${n === 1 ? one : many}`;

// One rule per kind of answer: the label the error words use, then length and shape. `norm`
// is what the field holds once tidied (codes upper-cased, hex lower-cased). The words are terse
// (owner, 17 Oct: "keep it modular"): the field's own label says what it is; the server refuses the
// same things (tephra.airline.models.AirlineAnswers).
export const RULES = {
  "airline.name": { label: "Airline name", required: true, min: 2, max: 120 },
  "airline.icao": { label: "ICAO designator", required: true, norm: upper, pattern: /^[A-Z]{3}$/, msg: "3 letters, A to Z" },
  "airline.iata": { label: "IATA code", norm: upper, pattern: /^[A-Z0-9]{2}$/, msg: "2 letters or digits" },
  "airline.callsign_prefix": { label: "Callsign prefix", required: true, norm: upper, pattern: /^[A-Z]{3}$/, msg: "3 letters, A to Z" },
  "airline.state_of_operator": { label: "State of the Operator", required: true, min: 2, max: 60 },
  "airline.aoc_number": { label: "AOC number", max: 40 },
  "airline.main_base": { label: "Main base", required: true, norm: upper, pattern: ICAO4, msg: "4 letters, A to Z" },
  "airline.ops_email": { label: "Operations email", required: true, max: 254, norm: (v) => str(v).toLowerCase(), pattern: EMAIL, msg: "Not an email" },
  "airline.contact_name": { label: "Contact name", max: 80 },
  "policy.value": { label: "Value", required: true, integer: [0, 100_000], msg: "Whole number, 0 to 100,000" },
  "policy.reason": { label: "Reason", required: true, min: 3, max: 300, minMsg: "3 to 300 characters", maxMsg: "3 to 300 characters" },
  "policy.risk_owner": { label: "Risk owner", required: true, min: 2, max: 80 },
  "policy.sra_ref": { label: "SRA reference", max: 120 },
  "fleet.registration": { label: "Registration", required: true, norm: upper, pattern: /^[A-Z0-9-]{2,10}$/, msg: "2 to 10 letters, digits or dashes" },
  "fleet.type_icao": { label: "Type", required: true, norm: upper, pattern: /^[A-Z0-9]{2,4}$/, msg: "ICAO type, e.g. A320" },
  "fleet.seats": { label: "Seats", required: true, integer: [0, 1000], msg: "Whole number, 0 to 1,000" },
  "fleet.home_base": { label: "Home base", norm: upper, pattern: ICAO4, msg: "4 letters, A to Z" },
  "fleet.hex": { label: "Hex address", norm: hexOf, pattern: /^[0-9a-f]{6}$/, msg: "6 characters, 0-9 and a-f" },
  "fleet.extra_prefixes": { label: "Other callsign prefix", norm: upper, pattern: /^[A-Z]{3}$/, msg: "3 letters, A to Z" },
  "network.icao": { label: "Airport", norm: upper, pattern: ICAO4, msg: "4 letters, A to Z" },
  "network.alternates": { label: "Alternate", norm: upper, pattern: ICAO4, msg: "4 letters, A to Z" },
  "feeds.source_system": { label: "Source system", max: 80 },
  "people.name": { label: "Name or initials", required: true, min: 2, max: 32, minMsg: "2 to 32 characters", maxMsg: "2 to 32 characters" },
  "people.role": { label: "Role", required: true, pattern: /^(approves|views)$/, msg: "Choose a role", needMsg: "Choose a role" },
  "assistant.provider": { label: "Where the model runs", required: true, pattern: /^(gemini|ollama|none)$/, msg: "Choose one", needMsg: "Choose one" },
  "assistant.gemini": { label: "Model", required: true, pattern: AI_STUDIO_MODEL, msg: "Gemini or Gemma name, e.g. gemini-3.8-flash" },
  "assistant.ollama": { label: "Model tag", required: true, pattern: OLLAMA_TAG, msg: "Ollama tag, e.g. gemma4:e4b" },
  "acct.email": { label: "Email", required: true, max: 254, norm: (v) => str(v).toLowerCase(), pattern: EMAIL, msg: "Not an email" },
  "acct.password": { label: "Password", required: true, min: 12, max: 128, minMsg: "12+ characters", maxMsg: "128 characters at most", raw: true },
  // a member's name in a hosted airline: the Desk's own name rule (2 to 32; letters, digits, . ' - _)
  "member.name": { label: "Your name", required: true, min: 2, max: 32, minMsg: "2 to 32 characters", maxMsg: "2 to 32 characters", norm: (v) => str(v).replace(/\s+/g, " "), pattern: /^[\p{L}\p{N} .'_-]+$/u, msg: "Letters, digits, spaces, . ' - _" },
};

// The words for one value against one rule, or null when it passes.
export function ruleMessage(kind, raw) {
  const r = RULES[kind];
  if (!r) return null;
  const v = r.raw ? (typeof raw === "string" ? raw : "") : str(raw);
  if (!v) return r.required ? r.needMsg || "Required" : null;
  if (CONTROL.test(v)) return "Plain text only";
  if (r.max && v.length > r.max) return r.maxMsg || `${r.max} characters at most`;
  if (r.min && v.length < r.min) return r.minMsg || `${r.min}+ characters`;
  if (r.integer) {
    const [lo, hi] = r.integer;
    return /^\d+$/.test(v) && Number(v) >= lo && Number(v) <= hi ? null : r.msg;
  }
  if (r.pattern && !r.pattern.test(r.norm ? r.norm(v) : v)) return r.msg;
  return null;
}

// The rule a field id answers to: "fleet.aircraft.3.hex" -> "fleet.hex".
export function kindOf(field) {
  const parts = field.split(".");
  if (parts[0] === "fleet" && parts[1] === "aircraft") return `fleet.${parts[3]}`;
  if (parts[0] === "fleet" && parts[1] === "extra_prefixes") return "fleet.extra_prefixes";
  if (parts[0] === "people") return `people.${parts[3]}`;
  if (parts[0] === "network" && parts[1] === "alternates") return "network.alternates";
  if (parts[0] === "network") return "network.icao";
  if (parts[0] === "policy" && parts[1] === "v") return "policy.value";
  if (parts[0] === "policy" && parts[1] === "r") return "policy.reason";
  return field;
}

// One problem as Review and the workspace say it: the page, then the field, then the terse words
// ("Fleet · Registration, row 2: Required").
export function problemText(key, { field, message }) {
  const parts = String(field || "").split(".");
  const kind = kindOf(parts.join("."));
  const policyName = parts[0] === "policy" && (parts[1] === "v" || parts[1] === "r") ? parts.slice(2).join(".") : null;
  const label = policyName ? `${KEY_POLICY_VALUES.find(([n]) => n === policyName)?.[1] || policyName}${parts[1] === "r" ? " reason" : ""}` : RULES[kind]?.label;
  const row = (parts[0] === "fleet" && parts[1] === "aircraft") || parts[0] === "people" ? Number(parts[2]) + 1 : NaN;
  const where = label ? ` · ${label}${Number.isFinite(row) ? `, row ${row}` : ""}` : "";
  return `${pageOf(key)?.short || key}${where}: ${message}`;
}

// --- the answers each page holds --------------------------------------------------------------------

export function emptyValues() {
  return {
    airline: {},
    policy: { preset: "A", changes: {} },
    fleet: { aircraft: [], extra_prefixes: [] },
    network: { airports: [], alternates: {} },
    schedule: { skipped: false, summary: null },
    feeds: {},
    people: { dispatchers: [] },
    assistant: { provider: null },
  };
}

// The policy values a draft changed: those whose number differs from Policy A's.
export function changedValues(values) {
  return Object.entries(values?.policy?.changes || {})
    .filter(([, c]) => c && /^\d+$/.test(str(c.value)) && Number(c.value) !== Number(c.base))
    .map(([name, c]) => ({ name, value: Number(c.value), reason: str(c.reason), base: Number(c.base), unit: c.unit || "" }));
}

const networkCodes = (values) => {
  const main = upper(values?.airline?.main_base);
  const rest = (values?.network?.airports || []).map(upper).filter((c) => c && c !== main);
  return [...(main ? [main] : []), ...rest];
};

export function checkPage(key, values, ctx = {}) {
  const out = [];
  const add = (field, raw, kind = kindOf(field)) => {
    const message = ruleMessage(kind, raw);
    if (message) out.push({ field, message });
    return !message;
  };
  const v = values || emptyValues();
  if (key === "airline") {
    for (const f of ["name", "icao", "iata", "callsign_prefix", "state_of_operator", "aoc_number", "main_base", "ops_email", "contact_name"]) add(`airline.${f}`, v.airline?.[f]);
  } else if (key === "policy") {
    const named = ctx.named || {};
    const changes = v.policy?.changes || {};
    const valueOf = (name) => (changes[name] && str(changes[name].value) !== "" ? Number(changes[name].value) : named[name]?.value);
    for (const [name, c] of Object.entries(changes)) {
      if (!c || str(c.value) === "" || Number(c.value) === Number(c.base)) continue;
      if (!add(`policy.v.${name}`, c.value)) continue;
      if (POSITIVE_POLICY_VALUES.includes(name) && Number(c.value) <= 0) out.push({ field: `policy.v.${name}`, message: "Above 0: a zero switches this check off" });
      add(`policy.r.${name}`, c.reason);
    }
    const divert = valueOf("planner.divert_within_min");
    const hold = valueOf("planner.hold_within_min");
    if (Number.isFinite(divert) && Number.isFinite(hold) && divert > hold) out.push({ field: "policy.v.planner.divert_within_min", message: "Not later than the hold time" });
    const bandFl = valueOf("planner.level_band_fl");
    const maxFl = valueOf("planner.max_change_level_fl");
    if (Number.isFinite(bandFl) && Number.isFinite(maxFl) && bandFl > maxFl) out.push({ field: "policy.v.planner.level_band_fl", message: "Not above the highest level proposed" });
    add("policy.risk_owner", v.policy?.risk_owner);
    if (changedValues(v).length && !str(v.policy?.sra_ref)) out.push({ field: "policy.sra_ref", message: "Required once a value changes" });
    else add("policy.sra_ref", v.policy?.sra_ref);
  } else if (key === "fleet") {
    const rows = v.fleet?.aircraft || [];
    if (!rows.length) out.push({ field: "fleet.aircraft", message: "Add an aircraft" });
    if (rows.length > 1000) out.push({ field: "fleet.aircraft", message: "1,000 aircraft at most" });
    const seenReg = new Map();
    const seenHex = new Map();
    rows.forEach((row, i) => {
      for (const f of ["registration", "type_icao", "seats", "home_base", "hex"]) add(`fleet.aircraft.${i}.${f}`, row?.[f]);
      const reg = upper(row?.registration);
      const hex = hexOf(row?.hex);
      if (reg && seenReg.has(reg)) out.push({ field: `fleet.aircraft.${i}.registration`, message: `Already on row ${seenReg.get(reg) + 1}` });
      else if (reg) seenReg.set(reg, i);
      if (hex && seenHex.has(hex)) out.push({ field: `fleet.aircraft.${i}.hex`, message: `Already on row ${seenHex.get(hex) + 1}` });
      else if (hex) seenHex.set(hex, i);
    });
    const prefixes = (v.fleet?.extra_prefixes || []).map(upper);
    if (prefixes.length > 4) out.push({ field: "fleet.extra_prefixes", message: "4 at most" });
    prefixes.forEach((p, i) => {
      if (!add(`fleet.extra_prefixes.${i}`, p, "fleet.extra_prefixes")) return;
      if (p === upper(v.airline?.callsign_prefix)) out.push({ field: `fleet.extra_prefixes.${i}`, message: "Already your callsign prefix" });
      else if (prefixes.indexOf(p) !== i) out.push({ field: `fleet.extra_prefixes.${i}`, message: "Already in the list" });
    });
  } else if (key === "network") {
    const codes = networkCodes(v);
    if (!codes.length) out.push({ field: "network.airports", message: "Add an airport" });
    if (codes.length > 200) out.push({ field: "network.airports", message: "200 airports at most" });
    codes.forEach((code, i) => {
      add(`network.airports.${i}`, code, "network.icao");
      const alts = (v.network?.alternates?.[code] || []).map(upper);
      if (alts.length > 5) out.push({ field: `network.alternates.${code}`, message: "5 at most" });
      alts.forEach((alt, j) => {
        if (!add(`network.alternates.${code}`, alt, "network.alternates")) return;
        if (alt === code) out.push({ field: `network.alternates.${code}`, message: "Not its own alternate" });
        else if (alts.indexOf(alt) !== j) out.push({ field: `network.alternates.${code}`, message: `${alt} is already listed` });
      });
    });
  } else if (key === "schedule") {
    const s = ctx.schedule;
    if (s && !s.ok) out.push({ field: "schedule.files", message: "Fix or remove the file" });
  } else if (key === "feeds") {
    add("feeds.source_system", v.feeds?.source_system);
  } else if (key === "people") {
    const rows = v.people?.dispatchers || [];
    if (!rows.length) out.push({ field: "people.dispatchers", message: "Add someone who approves" });
    if (rows.length > 50) out.push({ field: "people.dispatchers", message: "50 at most" });
    rows.forEach((row, i) => {
      add(`people.dispatchers.${i}.name`, row?.name);
      add(`people.dispatchers.${i}.role`, row?.role);
    });
    if (rows.length && !rows.some((r) => r?.role === "approves")) out.push({ field: "people.dispatchers", message: "Add someone who approves" });
  } else if (key === "assistant") {
    const a = v.assistant || {};
    if (add("assistant.provider", a.provider) && a.provider !== "none") {
      const kind = a.provider === "gemini" ? "assistant.gemini" : "assistant.ollama";
      add("assistant.model", a.model, kind);
      add("assistant.model_lite", a.model_lite, kind);
    }
  }
  return out;
}

// Non-blocking cautions: the page says them and lets the person go on.
export function cautionsOf(key, values, ctx = {}) {
  const out = [];
  if (key === "network") {
    const known = ctx.airports;
    const codes = networkCodes(values);
    if (known) for (const code of codes) if (ICAO4.test(code) && !known.has(code)) out.push({ field: `network.airport.${code}`, code, message: "Not in TEPHRA's list: no TAF, closure or diversion checks." });
    const outside = codes.filter((code) => ctx.positions?.[code] && !(ctx.regions || []).some((r) => inBox(r.bbox, ctx.positions[code])));
    if (outside.length) out.push({ field: "network.coverage", codes: outside, message: `Outside live ash coverage (Java and Bali, Halmahera, Kyushu): ${outside.join(", ")}.` });
  } else if (key === "assistant") {
    const a = values?.assistant || {};
    if (a.provider === "gemini") {
      for (const f of ["model", "model_lite"]) {
        const m = str(a[f]);
        if (AI_STUDIO_MODEL.test(m) && !FREE_TIER_MODELS.includes(m)) out.push({ field: `assistant.${f}`, message: "No known free-tier limit for this model: TEPHRA never calls it (AI UNAVAILABLE)." });
      }
    }
  }
  return out;
}

export const inBox = (b, [lon, lat]) => Boolean(b) && lat >= b.south && lat <= b.north && lon >= b.west && lon <= b.east;

// Where a draft resumes: the first answer page not opened yet or with a problem, else Review.
// `ctxFor(key)` gives each page's checking context, as checkPage takes it.
export function firstUnfinished(draft, ctxFor = () => ({})) {
  const seen = draft?.seen || [];
  const values = { ...emptyValues(), ...(draft?.values || {}) };
  return ANSWER_PAGES.find((key) => !seen.includes(key) || checkPage(key, values, ctxFor(key)).length) || "review";
}

// --- draft <-> AirlineAnswers -----------------------------------------------------------------------

export function toAnswers(draft) {
  const v = draft?.values || emptyValues();
  const a = v.airline || {};
  const p = v.policy || {};
  const main = upper(a.main_base);
  const s = v.schedule || {};
  const summary = s.summary && !s.skipped ? s.summary : null;
  const provider = v.assistant?.provider ?? null;
  const model = (f) => (provider === "gemini" || provider === "ollama" ? orNull(v.assistant?.[f]) : null);
  return {
    format: ONBOARD_FORMAT,
    airline: {
      name: str(a.name),
      icao: upper(a.icao),
      iata: orNull(upper(a.iata)),
      callsign_prefix: upper(a.callsign_prefix),
      state_of_operator: str(a.state_of_operator),
      aoc_number: orNull(a.aoc_number),
      main_base: main,
      ops_email: str(a.ops_email).toLowerCase(),
      contact_name: orNull(a.contact_name),
    },
    policy: {
      preset: "A",
      changes: changedValues(v).map(({ name, value, reason }) => ({ name, value, reason })),
      risk_owner: str(p.risk_owner),
      sra_ref: orNull(p.sra_ref),
    },
    fleet: {
      aircraft: (v.fleet?.aircraft || []).map((row) => ({
        registration: upper(row.registration),
        type_icao: upper(row.type_icao),
        seats: /^\d+$/.test(str(row.seats)) ? Number(row.seats) : null,
        home_base: orNull(upper(row.home_base)),
        hex: orNull(hexOf(row.hex)),
      })),
      extra_prefixes: (v.fleet?.extra_prefixes || []).map(upper).filter(Boolean),
    },
    network: {
      airports: networkCodes(v).map((icao) => ({ icao, alternates: (v.network?.alternates?.[icao] || []).map(upper).filter(Boolean) })),
    },
    schedule: summary
      ? { provided: true, flights: summary.flights, tails: summary.tails, crews: summary.crews, crew_bases: summary.crew_bases }
      : { provided: false, flights: 0, tails: 0, crews: 0, crew_bases: [] },
    feeds: {
      positions: Boolean(v.feeds?.positions),
      flight_plans: Boolean(v.feeds?.flight_plans),
      pilot_reports: Boolean(v.feeds?.pilot_reports),
      source_system: orNull(v.feeds?.source_system),
    },
    people: { dispatchers: (v.people?.dispatchers || []).map((d) => ({ name: str(d.name), role: d.role })) },
    assistant: { provider, model: model("model"), model_lite: model("model_lite") },
  };
}

// The stored answers back into page values (edit mode). `named` is the active policy's values
// by name, so each change keeps Policy A's number beside it.
export function fromAnswers(answers, named = {}) {
  const v = emptyValues();
  if (!answers) return v;
  const a = answers.airline || {};
  v.airline = {
    name: a.name || "", icao: a.icao || "", iata: a.iata || "", callsign_prefix: a.callsign_prefix || "", callsign_touched: true,
    state_of_operator: a.state_of_operator || "", aoc_number: a.aoc_number || "", main_base: a.main_base || "",
    ops_email: a.ops_email || "", contact_name: a.contact_name || "",
  };
  v.policy = {
    preset: "A",
    changes: Object.fromEntries((answers.policy?.changes || []).map((c) => [c.name, { value: String(c.value), reason: c.reason, base: named[c.name]?.value ?? null, unit: named[c.name]?.unit || "" }])),
    risk_owner: answers.policy?.risk_owner || "",
    sra_ref: answers.policy?.sra_ref || "",
  };
  v.fleet = {
    aircraft: (answers.fleet?.aircraft || []).map((r) => ({ registration: r.registration, type_icao: r.type_icao, seats: String(r.seats), home_base: r.home_base || "", hex: r.hex || "" })),
    extra_prefixes: [...(answers.fleet?.extra_prefixes || [])],
  };
  const airports = answers.network?.airports || [];
  v.network = {
    airports: airports.map((x) => x.icao).filter((c) => c !== a.main_base),
    alternates: Object.fromEntries(airports.map((x) => [x.icao, [...(x.alternates || [])]])),
  };
  const s = answers.schedule || {};
  v.schedule = { skipped: !s.provided, summary: s.provided ? { flights: s.flights, tails: s.tails, crews: s.crews, crew_bases: [...(s.crew_bases || [])] } : null };
  v.feeds = { ...(answers.feeds || {}), source_system: answers.feeds?.source_system || "" };
  v.people = { dispatchers: (answers.people?.dispatchers || []).map((d) => ({ ...d })) };
  v.assistant = { provider: answers.assistant?.provider ?? null, model: answers.assistant?.model || "", model_lite: answers.assistant?.model_lite || "" };
  return v;
}

// --- summaries ---------------------------------------------------------------------------------------

const andList = (items) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);
const capFirst = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
export const PROVIDER_WORDS = {
  gemini: "Gemini or Gemma (your own key)",
  ollama: "Gemma on your computer (Ollama)",
  none: "No model (NO MODEL)",
};
// One line per page, eight words at most (Review and the workspace's Your answers).
export function summaryOf(page, answers) {
  const x = answers || {};
  switch (page) {
    case "airline": {
      const a = x.airline || {};
      return [a.name, a.icao].filter(Boolean).join(" · ") || "Not given";
    }
    case "policy": {
      const n = (x.policy?.changes || []).length;
      return n ? `Policy A · ${count(n, "value")} changed` : "Policy A · as given";
    }
    case "fleet": {
      const rows = x.fleet?.aircraft || [];
      if (!rows.length) return "Not given";
      return count(rows.length, "aircraft", "aircraft");
    }
    case "network": {
      const n = (x.network?.airports || []).length;
      return n ? count(n, "airport") : "Not given";
    }
    case "schedule": {
      const s = x.schedule || {};
      return s.provided ? `${count(s.flights, "flight")} · ${count(s.crews, "crew")}` : "Not given";
    }
    case "feeds": {
      const f = x.feeds || {};
      const kinds = [f.positions && "positions", f.flight_plans && "flight plans", f.pilot_reports && "pilot reports"].filter(Boolean);
      return kinds.length ? capFirst(andList(kinds)) : "Public ADS-B only";
    }
    case "people": {
      const n = (x.people?.dispatchers || []).length;
      return n ? count(n, "dispatcher") : "Not given";
    }
    case "assistant": {
      const a = x.assistant || {};
      if (!a.provider) return "Not given";
      return [PROVIDER_WORDS[a.provider], a.model].filter(Boolean).join(" · ");
    }
    default:
      return "";
  }
}

// --- server problems ---------------------------------------------------------------------------------

const ROW_LABEL = { registration: "registration", type_icao: "type", seats: "seats", home_base: "home base", hex: "hex" };

// One problem string of the app's 422 ("answers.fleet.aircraft.6.hex: String should match ...")
// as { page, field, text }: the page's own words for that field where the page knows it, else the
// server's message under Review. `answers` is what was sent, so a policy change's index finds
// its name.
export function mapServerProblem(problem, answers = null) {
  const at = String(problem).indexOf(": ");
  const loc = at < 0 ? "" : String(problem).slice(0, at);
  const serverText = at < 0 ? String(problem) : String(problem).slice(at + 2);
  const parts = loc.split(".");
  if (parts[0] === "" && /password/.test(serverText)) return { page: "review", field: "acct.password", text: "Your account: the password must not be your email." };
  if (parts[0] === "email" || parts[0] === "password") {
    const kind = `acct.${parts[0]}`;
    return { page: "review", field: kind, text: `Your account: ${parts[0] === "email" ? RULES[kind].msg : "12 characters or more, and not your email."}` };
  }
  if (parts[0] !== "answers" || !PAGE_KEYS.includes(parts[1])) return { page: "review", field: null, text: `Review: ${serverText}` };
  const page = pageOf(parts[1]);
  const rest = parts.slice(1);
  let field = rest.join(".");
  let kind = null;
  let row = null;
  if (rest[0] === "fleet" && rest[1] === "aircraft" && /^\d+$/.test(rest[2] || "") && rest[3]) {
    row = Number(rest[2]);
    kind = `fleet.${rest[3]}`;
  } else if (rest[0] === "people" && rest[1] === "dispatchers" && /^\d+$/.test(rest[2] || "") && rest[3]) {
    row = Number(rest[2]);
    kind = `people.${rest[3]}`;
  } else if (rest[0] === "policy" && rest[1] === "changes" && /^\d+$/.test(rest[2] || "")) {
    const name = answers?.policy?.changes?.[Number(rest[2])]?.name;
    if (name) {
      field = `policy.${rest[3] === "reason" ? "r" : "v"}.${name}`;
      return { page: page.key, field, text: `${page.name}: ${name}: ${serverText}` };
    }
  } else if (rest[0] === "airline" || rest[0] === "assistant" || rest[0] === "feeds" || (rest[0] === "policy" && rest.length === 2)) {
    kind = RULES[field] ? field : null;
  }
  const rule = kind ? RULES[kind] : null;
  if (!rule || !rule.msg) return { page: page.key, field, text: `${page.name}: ${serverText}` };
  if (row != null) {
    const label = ROW_LABEL[rest[3]] || rule.label.toLowerCase();
    const msg = rule.msg.toLowerCase().startsWith(label.split(" ")[0]) ? lowerFirst(rule.msg) : `${label}: ${rule.msg}`;
    return { page: page.key, field, text: `${page.name}: row ${row + 1} ${msg}` };
  }
  return { page: page.key, field, text: `${page.name}: ${rule.label}: ${rule.msg}` };
}

// --- files read in the browser -----------------------------------------------------------------------

export const FLEET_FILE_MAX_BYTES = 512 * 1024;
export const SCHEDULE_FILE_MAX_BYTES = 2 * 1024 * 1024;
const FLEET_COLUMNS = ["registration", "type_icao", "seats", "home_base", "hex"];

// A fleet file: CSV `registration,type,seats,home_base,hex` (header optional, comma or tab) or
// a fleet.json ({"tails": [{"tail", "type", "seats", "home_base"?, "hex"?}]}). Every row
// is checked as the table checks it; a refused row says its number and why. `existing` is the
// table now, so a row already there is refused rather than added twice.
export function parseFleetFile(text, name = "", existing = []) {
  const out = { rows: [], refused: [], error: null };
  if (typeof text !== "string" || !text.trim()) {
    out.error = "This file is empty.";
    return out;
  }
  if (text.length > FLEET_FILE_MAX_BYTES) {
    out.error = "This file is larger than 512 KB.";
    return out;
  }
  let records = [];
  const json = /\.json$/i.test(name) || /^\s*[[{]/.test(text);
  if (json) {
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      out.error = `This is not JSON: ${e.message}`;
      return out;
    }
    const tails = Array.isArray(data?.tails) ? data.tails : null;
    if (!tails) {
      out.error = 'A fleet.json holds {"tails": [...]}.';
      return out;
    }
    records = tails.map((t, i) => ({ row: i + 1, rec: { registration: t?.tail, type_icao: t?.type, seats: t?.seats == null ? "" : String(t.seats), home_base: t?.home_base || "", hex: t?.hex || "" } }));
  } else {
    const lines = text.split(/\r?\n/);
    lines.forEach((line, i) => {
      if (!line.trim()) return;
      const cells = line.split(line.includes("\t") ? "\t" : ",").map((c) => c.trim());
      if (i === 0 && /registration/i.test(cells[0] || "")) return;
      records.push({ row: i + 1, rec: Object.fromEntries(FLEET_COLUMNS.map((k, j) => [k, cells[j] ?? ""])) });
    });
  }
  const regs = new Set(existing.map((r) => upper(r.registration)).filter(Boolean));
  const hexes = new Set(existing.map((r) => hexOf(r.hex)).filter(Boolean));
  for (const { row, rec } of records) {
    let message = null;
    for (const f of FLEET_COLUMNS) {
      message = ruleMessage(`fleet.${f}`, rec[f]);
      if (message) {
        message = lowerFirst(message).startsWith(ROW_LABEL[f].split(" ")[0]) ? lowerFirst(message) : `${ROW_LABEL[f]}: ${message}`;
        break;
      }
    }
    const reg = upper(rec.registration);
    const hex = hexOf(rec.hex);
    if (!message && regs.has(reg)) message = `${reg} is already in your fleet.`;
    if (!message && hex && hexes.has(hex)) message = `hex ${hex} is already in your fleet.`;
    if (message) {
      out.refused.push({ row, message: `Row ${row}: ${message}` });
      continue;
    }
    regs.add(reg);
    if (hex) hexes.add(hex);
    out.rows.push({ registration: reg, type_icao: upper(rec.type_icao), seats: str(rec.seats), home_base: upper(rec.home_base), hex });
  }
  return out;
}

const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const ITEM_CODE = /^[A-Z]{4}$/;
const MAX_LISTED = 5;

function readJson(text) {
  try {
    return { data: JSON.parse(text) };
  } catch (e) {
    return { error: `This is not JSON: ${e.message}` };
  }
}

function checkFlights(text, registrations) {
  const res = { name: "flights.json", count: 0, problems: [], total: 0, tails: 0 };
  const note = (t) => {
    res.total += 1;
    if (res.problems.length < MAX_LISTED) res.problems.push(t);
  };
  if (text.length > SCHEDULE_FILE_MAX_BYTES) {
    note("This file is larger than 2 MB.");
    return res;
  }
  const { data, error } = readJson(text);
  if (error) {
    note(error);
    return res;
  }
  const h = data?.header;
  if (!h || typeof h !== "object") note('No "header": flights.json starts with {"header": {"label", "anchor_utc_offset_h"}}.');
  else if (typeof h.anchor_utc_offset_h !== "number" || h.anchor_utc_offset_h < -12 || h.anchor_utc_offset_h > 14) note("header.anchor_utc_offset_h is a number of hours from -12 to 14.");
  const flights = Array.isArray(data?.flights) ? data.flights : null;
  if (!flights) {
    note('No "flights" list.');
    return res;
  }
  const regs = new Set(registrations.map(upper));
  const tails = new Set();
  flights.forEach((f, i) => {
    const at = `Flight ${i + 1}`;
    if (!f || typeof f !== "object") return note(`${at}: not an object.`);
    if (!/^[A-Z0-9]{3,8}$/.test(String(f.flight_no ?? ""))) note(`${at}: flight_no is 3 to 8 capital letters or digits.`);
    if (!ITEM_CODE.test(String(f.origin ?? "")) || !ITEM_CODE.test(String(f.dest ?? ""))) note(`${at}: origin and dest are ICAO airport codes, four capital letters.`);
    else if (f.origin === f.dest) note(`${at}: origin and dest are the same airport.`);
    if (!isInt(f.std_min, 0, 2879)) note(`${at}: std_min is a whole number of minutes from 0 to 2879.`);
    if (!Number.isInteger(f.block_min) || f.block_min <= 0) note(`${at}: block_min is a whole number of minutes above 0.`);
    if (f.callsign != null && !/^[A-Z0-9]{2,8}$/.test(String(f.callsign))) note(`${at}: callsign is 2 to 8 capital letters or digits.`);
    if (f.days != null && !/^[1-7]{1,7}$/.test(String(f.days))) note(`${at}: days is a list of weekdays 1 to 7 (1 is Monday).`);
    if (f.pax_booked != null && !isInt(f.pax_booked, 0, 1000)) note(`${at}: pax_booked is a whole number from 0 to 1000.`);
    if (f.tail != null) {
      if (!regs.has(upper(f.tail))) note(`${at}: tail ${String(f.tail).slice(0, 12)} is not in your fleet.`);
      else tails.add(upper(f.tail));
    }
  });
  res.count = flights.length;
  res.tails = tails.size;
  return res;
}

function checkCrews(text) {
  const res = { name: "crews.json", count: 0, problems: [], total: 0, bases: [] };
  const note = (t) => {
    res.total += 1;
    if (res.problems.length < MAX_LISTED) res.problems.push(t);
  };
  if (text.length > SCHEDULE_FILE_MAX_BYTES) {
    note("This file is larger than 2 MB.");
    return res;
  }
  const { data, error } = readJson(text);
  if (error) {
    note(error);
    return res;
  }
  const crews = Array.isArray(data?.crews) ? data.crews : null;
  if (!crews) {
    note('No "crews" list: crews.json holds {"crews": [...]}.');
    return res;
  }
  const bases = new Set();
  crews.forEach((c, i) => {
    const at = `Crew ${i + 1}`;
    if (!c || typeof c !== "object") return note(`${at}: not an object.`);
    if (typeof c.crew_id !== "string" || !c.crew_id.trim() || c.crew_id.length > 40) note(`${at}: crew_id is a name of 1 to 40 characters.`);
    if (!ITEM_CODE.test(String(c.base ?? ""))) note(`${at}: base is an ICAO airport code, four capital letters.`);
    else bases.add(c.base);
    if (!isInt(c.report_min, 0, 2879)) note(`${at}: report_min is a whole number of minutes from 0 to 2879.`);
  });
  res.count = crews.length;
  res.bases = [...bases].sort();
  return res;
}

// The two schedule files as text ({flights, crews}, either may be null), checked against the
// fleet's registrations. `summary` is set only when both were read without a problem.
export function checkSchedule(files, registrations = []) {
  const flights = files?.flights ? checkFlights(files.flights, registrations) : null;
  const crews = files?.crews ? checkCrews(files.crews) : null;
  const ok = (!flights || flights.total === 0) && (!crews || crews.total === 0);
  const summary = flights && crews && ok
    ? { flights: flights.count, tails: flights.tails, crews: crews.count, crew_bases: crews.bases.slice(0, 50) }
    : null;
  return { flights, crews, ok, summary };
}

export const fileLine = (r) => `${r.name} · ${count(r.count, r.name === "flights.json" ? "flight" : "crew")} · ${count(r.total, "problem")}`;

// --- the Network page's "Add an airport" -------------------------------------------------------------

// `airports`: a Map (or an object) of ICAO code -> { name, iata }, TEPHRA's airport list. An exact
// ICAO code in the list wins, then its IATA code, then a single name match; four letters become a
// code TEPHRA does not know only when no name matches ("Kobe" is RJBE, never KOBE). Null when
// nothing or more than one airport matches.
export function airportCode(text, airports) {
  const list = airports instanceof Map ? [...airports] : Object.entries(airports || {});
  const t = str(text).trim();
  const head = t.split("·")[0].trim().toUpperCase();
  if (list.some(([code]) => code === head)) return head;
  const byIata = list.find(([, ap]) => ap && ap.iata && ap.iata.toUpperCase() === head);
  if (byIata) return byIata[0];
  const low = t.toLowerCase();
  if (low.length >= 3) {
    const named = list.filter(([, ap]) => (ap?.name || "").toLowerCase().includes(low));
    const exact = named.filter(([, ap]) => ap.name.toLowerCase() === low);
    if (exact.length === 1) return exact[0][0];
    if (named.length === 1) return named[0][0];
    if (named.length > 1) return null;
  }
  return /^[A-Z]{4}$/.test(head) ? head : null;
}

// --- where a ?next= may send a signed-in airline (no open redirect) ----------------------------------

const NEXT_OK = [
  /^\/workspace(\/(answers|feeds|assistant))?$/,
  /^\/onboard\/(airline|policy|fleet|network|schedule|feeds|people|assistant)\?edit=1$/,
  // a hosted airline's pages (/a/<ICAO>/...) and the invite page; one slash at a time, no dots
  /^\/a\/[A-Z]{3}(\/([A-Za-z0-9_-]+(\/[A-Za-z0-9_-]+)*\/?)?)?$/,
  /^\/join$/,
];
export function safeNext(next) {
  const n = typeof next === "string" ? next : "";
  return NEXT_OK.some((re) => re.test(n)) ? n : "/workspace";
}
