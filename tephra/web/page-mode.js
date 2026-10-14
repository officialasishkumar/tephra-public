// Which view of the Wall's page this is, set before the page is drawn (no flash of the Wall):
// /assistant shows the TEPHRA Assistant board as the page (UI-DESIGN 7.27).
document.documentElement.dataset.page = location.pathname.replace(/\/+$/, "") === "/assistant" ? "assistant" : "wall";
