// The theme a reader picked (theme.js), applied before the page draws. Without a stored choice the
// page follows the system. A classic script, first in the head; dark-only pages never load it.
(function () {
  try {
    var theme = localStorage.getItem("tephra.theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch (e) {
    /* storage blocked: follow the system */
  }
})();
