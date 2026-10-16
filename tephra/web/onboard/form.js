// DOM builders for the onboarding and workspace forms (docs/UI-DESIGN.md: a label above every
// field, the hint under it, the error under that in words with a shape, tied to the field by
// aria-describedby). Text goes in through el() (textContent) only.

import { el, icon } from "../wall/util.js";

// A field key ("fleet.aircraft.3.hex") as a DOM id.
export const fid = (field) => `f-${field.replace(/[^A-Za-z0-9]+/g, "-")}`;

// label, then the control (or `slot`, a wrapper holding it), then the hint and the error;
// `hint` may be a node.
export function field({ id, label, optional = false, hint = null, control, slot = null, cls = "" }) {
  const hintId = hint ? `${id}-hint` : null;
  const errId = `${id}-err`;
  control.id = id;
  control.setAttribute("aria-describedby", [hintId, errId].filter(Boolean).join(" "));
  return el("div", { class: `field ${cls}`.trim() },
    el("label", { for: id }, label, optional ? el("span", { class: "opt", text: " (optional)" }) : null),
    slot || control,
    hint ? el("p", { id: hintId, class: "hint" }, hint) : null,
    el("p", { id: errId, class: "err", hidden: true }));
}

export function input({ value = "", mono = false, type = "text", ...attrs } = {}) {
  return el("input", { class: `input${mono ? " mono" : ""}`, type, value: value ?? "", spellcheck: mono ? "false" : null, autocapitalize: mono ? "characters" : null, ...attrs });
}

// Show or clear the words under a control; the error node is "<id>-err".
export function setError(control, message) {
  const err = document.getElementById(`${control.id}-err`);
  control.setAttribute("aria-invalid", message ? "true" : "false");
  if (!err) return;
  err.hidden = !message;
  err.replaceChildren(...(message ? [icon("i-alert"), el("span", { text: message })] : []));
}

// An error for a whole list (no single control): a role=alert-free line with an id the list's
// controls point at.
export const listError = (id) => el("p", { id: `${id}-err`, class: "err", hidden: true });
export function setListError(id, message) {
  const err = document.getElementById(`${id}-err`);
  if (!err) return;
  err.hidden = !message;
  err.replaceChildren(...(message ? [icon("i-alert"), el("span", { text: message })] : []));
}

export function section(title, id, ...kids) {
  return el("section", { class: "section", "aria-labelledby": id }, el("h2", { id, text: title }), ...kids);
}

// kind: info | caution | notbuilt
export function note(kind, lead, text, { role = null } = {}) {
  const shape = kind === "caution" ? "st-caution" : "i-info";
  return el("div", { class: `note note--${kind}`, role }, icon(shape), el("p", {}, lead ? el("b", { text: `${lead} ` }) : null, text));
}

export const illus = () => el("span", { class: "chip chip--illus", text: "ILLUSTRATIVE" });
export const notBuilt = () => el("span", { class: "chip chip--notbuilt", text: "Not built" });

// Native radios in labelled cards (role=radiogroup); `disabled` cards show their reason.
export function choiceCards({ name, legend, options, value, onChange }) {
  const group = el("div", { class: "choices", role: "radiogroup", "aria-label": legend });
  for (const o of options) {
    const radio = el("input", { type: "radio", name, value: o.value, checked: value === o.value, disabled: o.disabled || null, "aria-describedby": o.reason ? `${name}-${o.value}-why` : null });
    radio.addEventListener("change", () => {
      if (radio.checked) onChange(o.value);
    });
    group.append(el("label", { class: `choice${o.disabled ? " is-disabled" : ""}` },
      radio,
      el("span", { class: "choice__body" },
        el("span", { class: "choice__title" }, el("b", { text: o.title }), ...(o.chips || [])),
        el("span", { class: "choice__text", text: o.text }),
        o.reason ? el("span", { id: `${name}-${o.value}-why`, class: "choice__why", text: o.reason }) : null)));
  }
  return group;
}

// A segmented tab control (the ARIA tabs pattern: arrows move, Home/End jump).
export function segmented({ label, tabs, value, onChange, idBase }) {
  const list = el("div", { class: "seg", role: "tablist", "aria-label": label });
  const buttons = tabs.map((t) => {
    const b = el("button", { type: "button", role: "tab", id: `${idBase}-${t.key}`, "aria-controls": `${idBase}-panel`, "aria-selected": String(t.key === value), tabindex: t.key === value ? "0" : "-1" },
      t.icon ? icon(t.icon) : null, el("span", { text: t.text }));
    b.addEventListener("click", () => onChange(t.key));
    return b;
  });
  list.append(...buttons);
  list.addEventListener("keydown", (e) => {
    const i = buttons.indexOf(document.activeElement);
    if (i < 0) return;
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: buttons.length - 1 }[e.key];
    if (j == null) return;
    e.preventDefault();
    const k = (j + buttons.length) % buttons.length;
    onChange(tabs[k].key);
    document.getElementById(`${idBase}-${tabs[k].key}`)?.focus();
  });
  return list;
}

// A list of short codes typed one at a time (Enter or comma adds, each chip removable by a
// named button). `normalise` tidies what is typed; `onChange` gets the new list.
export function chipsInput({ id, label, values, max, onChange, normalise = (v) => v.trim().toUpperCase(), placeholder = "", describedBy = "" }) {
  const box = el("div", { class: "tokens" });
  const typed = el("input", { id, class: "tokens__in mono", type: "text", spellcheck: "false", autocapitalize: "characters", autocomplete: "off", placeholder, "aria-describedby": describedBy || null });
  const draw = () => {
    box.replaceChildren(...values.map((v, i) => {
      const remove = el("button", { type: "button", "aria-label": `Remove ${v}` }, icon("i-x"));
      remove.addEventListener("click", () => {
        values = values.filter((_, j) => j !== i);
        onChange(values);
        draw();
        typed.focus();
      });
      return el("span", { class: "tok" }, el("span", { text: v }), remove);
    }), typed);
    typed.disabled = values.length >= max;
    typed.setAttribute("aria-label", `${label}${values.length ? `: ${values.join(", ")}` : ""}${values.length >= max ? ` (at most ${max})` : ""}`);
  };
  const add = () => {
    const v = normalise(typed.value.replace(/,/g, ""));
    typed.value = "";
    if (!v || values.length >= max) return;
    values = [...values, v];
    onChange(values);
    draw();
    typed.focus();
  };
  typed.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && !typed.value && values.length) {
      values = values.slice(0, -1);
      onChange(values);
      draw();
      typed.focus();
    }
  });
  typed.addEventListener("blur", () => {
    if (typed.value.trim()) add();
  });
  draw();
  return box;
}

// Show / Hide on a password field (aria-pressed, aria-controls).
export function passwordInput({ id, autocomplete }) {
  const control = el("input", { class: "input", type: "password", autocomplete, spellcheck: "false", autocapitalize: "off" });
  const toggle = el("button", { type: "button", class: "pwshow", "aria-controls": id, "aria-pressed": "false", text: "Show" });
  toggle.addEventListener("click", () => {
    const show = control.type === "password";
    control.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-pressed", String(show));
  });
  return { control, wrap: (node) => el("div", { class: "pwwrap" }, node, toggle) };
}

export const caret = () => icon("i-chevron-down", "icon chev");
