// The theme control: System, Light or Dark (DESIGN 3). It writes data-theme on <html> (none for
// System, so the page follows the OS) and remembers the choice in this browser; theme-boot.js
// applies it on the next page before it draws. The page renders correctly without storage.

import { el } from "./wall/util.js";

const KEY = "tephra.theme";
const CHOICES = [["system", "System"], ["light", "Light"], ["dark", "Dark"]];
let made = 0;

export function currentTheme() {
  const t = document.documentElement.dataset.theme;
  return t === "light" || t === "dark" ? t : "system";
}

export function setTheme(choice) {
  const root = document.documentElement;
  if (choice === "light" || choice === "dark") root.dataset.theme = choice;
  else delete root.dataset.theme;
  try {
    if (choice === "light" || choice === "dark") localStorage.setItem(KEY, choice);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage blocked: the choice holds for this page only */
  }
}

export function themeControl() {
  made += 1;
  const name = `theme-${made}`;
  const labelId = `${name}-label`;
  const now = currentTheme();
  const group = el("div", { class: "theme-pick", role: "radiogroup", "aria-labelledby": labelId },
    el("span", { id: labelId, class: "theme-pick__label", text: "Theme" }),
    CHOICES.map(([value, text]) => el("label", { class: "theme-pick__opt" },
      el("input", { type: "radio", name, value, checked: value === now }),
      el("span", { text }))));
  group.addEventListener("change", (e) => {
    if (e.target.name === name) setTheme(e.target.value);
  });
  return group;
}
