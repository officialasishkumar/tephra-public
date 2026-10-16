// The assistant's model: the three choice cards of onboarding page 8 (shared with the workspace's
// Assistant page, which saves the choice with PUT /api/airline/assistant in any status). Only the
// provider and the two model names are stored per airline; a Gemini key is never asked for here
// (it goes only into the setup kit, on the kit page), and the Ollama address stays in this browser.

import { el, icon } from "../wall/util.js";
import { DEFAULT_MODELS, DEFAULT_OLLAMA_URL, cautionsOf, checkPage } from "../onboard/pages.js";
import { choiceCards, fid, field, input, note, setError } from "../onboard/form.js";
import { loadLocal, saveLocal } from "../onboard/draft.js";
import { PATHS, call, failWords } from "./api.js";

const CARDS = [
  { value: "gemini", title: "Gemini or Gemma, with your own Google AI Studio key", text: "A key from your own Google project. Your key is never stored here: it goes only into your setup kit, in this browser. On Google's unpaid tier, what TEPHRA sends (public ash feeds and the facts code writes about your flights) may be used to improve Google's products (see the privacy page)." },
  { value: "ollama", title: "Gemma on your computer, through Ollama", text: "Nothing leaves your network. Needs a capable machine." },
  { value: "none", title: "No model", text: "Code checks only, labelled NO MODEL. Useful to try your fleet and feeds first." },
];

// a: { provider, model, model_lite }, changed in place. ollama: { get(), set(v) } for the
// browser-only address. onChange() hears every change; recheck(id) re-checks one field.
export function modelChoice(a, { ollama, onChange, recheck = () => {} }) {
  const fields = el("div", { class: "modelfields" });
  const drawFields = () => {
    fields.replaceChildren();
    if (a.provider !== "gemini" && a.provider !== "ollama") return;
    const [m1, m2] = DEFAULT_MODELS[a.provider];
    if (!a.model) a.model = m1;
    if (!a.model_lite) a.model_lite = m2;
    const isOllama = a.provider === "ollama";
    const caution = el("div", {});
    const defaults = el("p", { class: "hint" });
    const drawNotes = () => {
      caution.replaceChildren(...cautionsOf("assistant", { assistant: a }).map((c) => note("caution", null, c.message)));
      defaults.textContent = a.model === m1 && a.model_lite === m2 ? "TEPHRA's defaults." : "";
      defaults.hidden = !defaults.textContent;
    };
    const model = (key, label) => {
      const id = fid(`assistant.${key}`);
      const c = input({ mono: true, autocomplete: "off", maxlength: 101, value: a[key] });
      c.addEventListener("input", () => {
        a[key] = c.value.trim();
        drawNotes();
        if (c.getAttribute("aria-invalid") === "true") recheck(id);
        onChange();
      });
      return field({ id, label, control: c });
    };
    fields.append(el("div", { class: "row2" }, model("model", isOllama ? "Model tag" : "Model"), model("model_lite", isOllama ? "Lighter model tag" : "Lighter model")), defaults, caution);
    if (isOllama && ollama) {
      const id = fid("assistant.ollama_url");
      const c = input({ mono: true, type: "url", autocomplete: "off", value: ollama.get() });
      c.addEventListener("input", () => {
        ollama.set(c.value.trim());
        if (c.getAttribute("aria-invalid") === "true") recheck(id);
        onChange();
      });
      fields.append(field({ id, label: "Ollama address (stays in this browser, goes only into your kit)", hint: "TEPHRA's default is http://127.0.0.1:11434.", control: c }));
    }
    drawNotes();
  };
  const cards = choiceCards({
    name: "ob-provider", legend: "Where the model runs", value: a.provider, options: CARDS,
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
  const local = loadLocal();
  let url = local.ollama_url || DEFAULT_OLLAMA_URL;
  const status = el("p", { class: "ws-status", role: "status" });
  const save = el("button", { type: "submit", class: "btn btn--primary" }, el("span", { text: "Save" }));
  const check = () => {
    const problems = checkPage("assistant", { assistant: a }, { ollamaUrl: url });
    for (const id of [fid("assistant.model"), fid("assistant.model_lite"), fid("assistant.ollama_url")]) {
      const c = document.getElementById(id);
      if (c) setError(c, problems.find((p) => fid(p.field) === id)?.message || null);
    }
    return problems;
  };
  const form = el("form", { class: "card wcard", novalidate: true, "aria-labelledby": "as-h" },
    el("div", { class: "wcard__h" }, el("span", { class: "wcard__ic" }, icon("ta-16")), el("h2", { id: "as-h", text: "Where TEPHRA Assistant's model runs" })),
    modelChoice(a, { ollama: { get: () => url, set: (v) => { url = v; } }, onChange: () => { status.textContent = ""; }, recheck: check }),
    el("p", { class: "body2", text: "Your choice goes into your setup kit. Your own key is never stored here." }),
    el("div", { class: "wcard__foot" }, save),
    status);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const problems = check();
    if (problems.length) {
      status.textContent = `Not saved: ${problems[0].message}`;
      document.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    if (a.provider === "ollama") saveLocal({ ...loadLocal(), ollama_url: url });
    save.disabled = true;
    const res = await call(PATHS.assistant, { method: "PUT", body: { version, assistant: { provider: a.provider, model: a.provider === "none" ? null : a.model, model_lite: a.provider === "none" ? null : a.model_lite } } });
    save.disabled = false;
    if (res.ok && res.data) {
      version = res.data.version;
      status.textContent = "Saved. Your next setup kit uses it.";
      onSaved(res.data);
      return;
    }
    status.textContent = res.status === 409 ? "Someone changed your workspace in another tab. Reload to see it." : res.status === 422 ? "Not saved: the server refused these model names." : failWords(res);
  });
  main.append(form);
}
