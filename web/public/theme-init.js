// Runs before the first paint. It is its own file because the page's security policy does not allow inline scripts.
//  1. A saved light or dark choice is applied, so the other one never flashes.
//  2. The opening logo screen is decided: shown once per tab, forced with ?splash=1, never with ?splash=0.
//     A reload in the middle of an exam therefore never waits for it. web/src/splash.ts holds the same rule and a test keeps them equal.
(function () {
  var root = document.documentElement;
  try {
    var mode = localStorage.getItem("tutor-mode");
    if (mode === "light" || mode === "dark") root.setAttribute("data-mode", mode);
  } catch (e) {
    /* storage can be blocked: the system setting is used instead */
  }
  var show = false;
  try {
    var asked = /[?&]splash=([01])(?:&|$)/.exec(location.search);
    var seen = sessionStorage.getItem("tutor-splash") === "1";
    show = asked ? asked[1] === "1" : !seen;
    if (show) sessionStorage.setItem("tutor-splash", "1");
  } catch (e) {
    show = false; // cannot remember it, so never delay a reload
  }
  root.setAttribute("data-splash", show ? "show" : "skip");
})();
