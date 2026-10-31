// Runs before the first paint so a saved light or dark choice never flashes the other one.
// It is a separate file because the page's security policy does not allow inline scripts.
(function () {
  try {
    var mode = localStorage.getItem("tutor-mode");
    if (mode === "light" || mode === "dark") document.documentElement.setAttribute("data-mode", mode);
  } catch (e) {
    /* storage can be blocked: the system setting is used instead */
  }
})();
