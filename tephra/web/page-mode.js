// Which view of the demo's page this is, set before the page is drawn (no flash of the demo):
// /assistant shows the TEPHRA Assistant board as the page (UI-DESIGN 7.27), dark only, whatever the
// theme (theme-boot.js runs first and may have set one).
{
  const assistant = location.pathname.replace(/\/+$/, "") === "/assistant";
  document.documentElement.dataset.page = assistant ? "assistant" : "wall";
  if (assistant) document.documentElement.dataset.theme = "dark";
}
