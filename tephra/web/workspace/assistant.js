// The assistant's model: the three choice cards of onboarding page 8 (shared with the workspace's
// Assistant page, which saves the choice with PUT /api/airline/assistant in any status). Only the
// provider and the two model names are stored with the answers; these pages never ask for a Gemini
// key. Where this site hosts airlines, the key is added later in the airline's own space (Settings ›
// Assistant), stored encrypted: the Gemini card's (i) says which, so it is true either way.
// Each card is a title and one line; the rest, the unpaid tier's data use among it, is behind the
// card's (i), heard with the card before it is chosen.

import { el, icon } from "../wall/util.js";
import { has } from "../wall/features.js";
import { DEFAULT_MODELS, cautionsOf, checkPage } from "../onboard/pages.js";
import { choiceCards, fid, field, input, note, setError } from "../onboard/form.js";
import { PATHS, call, failWords } from "./api.js";

const privacy = () => el("a", { class: "link", href: "/privacy", text: "Privacy" });
// Where the key goes: hosting off, this site never takes it; hosting on, the airline's space keeps it.
export const KEY_OFF = "Your own Google AI Studio key; this site never stores it.";
export const KEY_HOSTED = "Your own Google AI Studio key, added in your airline's space once hosting is approved and stored encrypted there.";
const DATA_USE = "TEPHRA sends it public ash feeds and the facts code writes about your flights. On Google's unpaid tier, what TEPHRA sends may be used to improve Google's products.";
const modelCards = (hosted) => [
  {
    value: "gemini", title: "Gemini or Gemma (your own key)", text: "Your key · data use",
    info: { topic: "your key and data use", label: "About your key and data use", text: `${hosted ? KEY_HOSTED : KEY_OFF} ${DATA_USE}`, actions: [privacy()] },
  },
  { value: "ollama", title: "Gemma on your computer (Ollama)", text: "Stays on your network.", info: { topic: "Ollama", label: "About Ollama", text: "Runs on a machine you own. It needs a capable one." } },
  { value: "none", title: "No model", text: "Code checks only, marked { }." },
];

// a: { provider, model, model_lite }, changed in place. onChange() hears every change;
// recheck(id) re-checks one field.
export function modelChoice(a, { onChange, recheck = () => {} }) {
  const fields = el("div", { class: "modelfields" });
  const drawFields = () => {
    fields.replaceChildren();
    if (a.provider !== "gemini" && a.provider !== "ollama") return;
    const [m1, m2] = DEFAULT_MODELS[a.provider];
    if (!a.model) a.model = m1;
    if (!a.model_lite) a.model_lite = m2;
    const isOllama = a.provider === "ollama";
    const caution = el("div", {});
    const drawNotes = () => {
      caution.replaceChildren(...cautionsOf("assistant", { assistant: a }).map((c) => note("caution", null, c.message)));
    };
    const model = (key, label) => {
      const id = fid(`assistant.${key}`);
      const c = input({ mono: true, autocomplete: "off", maxlength: 101, value: a[key] });
      c.addEventListener("input", () => {
        c.dataset.typed = "1";
        a[key] = c.value.trim();
        drawNotes();
        if (c.getAttribute("aria-invalid") === "true") recheck(id);
        onChange();
      });
      c.addEventListener("blur", () => {
        if (c.dataset.typed) recheck(id);
      });
      return field({ id, label, control: c });
    };
    fields.append(el("div", { class: "row2" }, model("model", isOllama ? "Model tag" : "Model"), model("model_lite", isOllama ? "Lighter model tag" : "Lighter model")), caution);
    drawNotes();
  };
  const cards = choiceCards({
    name: "ob-provider", legend: "Where the model runs", value: a.provider, options: modelCards(has("hosted")),
    onChange: (v) => {
      if (a.provider !== v) {
        a.model = v === "none" ? null : "";
        a.model_lite = v === "none" ? null : "";
      }
      a.provider = v;
      drawFields();
      onChange();
    },
  });
  cards.id = fid("assistant.provider");
  drawFields();
  return el("div", {}, cards, el("p", { id: `${fid("assistant.provider")}-err`, class: "err", hidden: true, dataset: { list: fid("assistant.provider") } }), fields);
}

// /workspace/assistant: the stored choice, saved in every status.
export function renderAssistant(main, view, { onSaved }) {
  const a = { ...view.answers.assistant };
  let version = view.version;
  const status = el("p", { class: "ws-status", role: "status" });
  const save = el("button", { type: "submit", class: "btn btn--primary" }, el("span", { text: "Save" }));
  const check = () => {
    const problems = checkPage("assistant", { assistant: a });
    for (const id of [fid("assistant.model"), fid("assistant.model_lite")]) {
      const c = document.getElementById(id);
      if (c) setError(c, problems.find((p) => fid(p.field) === id)?.message || null);
    }
    return problems;
  };
  const form = el("form", { class: "card wcard", novalidate: true, "aria-labelledby": "as-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic" }, icon("ta-16")), el("h2", { id: "as-h", text: "Where the model runs" })),
    modelChoice(a, { onChange: () => { status.textContent = ""; }, recheck: check }),
    el("div", { class: "wcard__foot" }, save),
    status);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const problems = check();
    if (problems.length) {
      status.textContent = "Not saved: check the fields marked.";
      document.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    save.disabled = true;
    const res = await call(PATHS.assistant, { method: "PUT", body: { version, assistant: { provider: a.provider, model: a.provider === "none" ? null : a.model, model_lite: a.provider === "none" ? null : a.model_lite } } });
    save.disabled = false;
    if (res.ok && res.data) {
      version = res.data.version;
      status.textContent = "Saved.";
      onSaved(res.data);
      return;
    }
    status.textContent = res.status === 409 ? "Someone changed your workspace in another tab. Reload to see it." : res.status === 422 ? "Not saved: the server refused these model names." : failWords(res);
  });
  main.append(form);
}
