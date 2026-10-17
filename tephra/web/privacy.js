// The privacy notice's sections are closed under their headings; a link that names one
// (/privacy#accounts, or #accounts from another section) opens it and brings it into view.

function openNamed() {
  const at = location.hash ? document.getElementById(location.hash.slice(1)) : null;
  const fold = at ? at.closest("details") : null;
  if (!fold) return;
  fold.open = true;
  at.scrollIntoView({ block: "start" });
}

window.addEventListener("hashchange", openNamed);
openNamed();
