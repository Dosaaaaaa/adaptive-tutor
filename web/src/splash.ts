// The opening logo screen. Its markup is in index.html and its 4 seconds are kept by splash.css, so this file only
// makes it skippable and keeps the app behind it out of reach until it has gone.

/** Whether the screen shows: once per tab, forced with ?splash=1, never with ?splash=0. public/theme-init.js holds the same rule. */
export function shouldShowSplash(search: string, seen: boolean): boolean {
  const asked = new URLSearchParams(search).get("splash");
  if (asked === "1") return true;
  if (asked === "0") return false;
  return !seen;
}

const SAFETY_MS = 6000;

export function startSplash(): void {
  const splash = document.getElementById("splash");
  if (!splash) return;
  const decided = document.documentElement.dataset.splash;
  let seen = false;
  try {
    seen = sessionStorage.getItem("tutor-splash") === "1";
  } catch {
    seen = true; // cannot remember it, so never delay a reload
  }
  const show = decided ? decided === "show" : shouldShowSplash(window.location.search, seen);
  if (!show) {
    splash.remove();
    return;
  }

  const root = document.getElementById("root");
  root?.setAttribute("inert", ""); // nothing behind the logo can be reached by keyboard or screen reader while it is up
  let done = false;

  const finish = () => {
    if (done) return;
    done = true;
    window.removeEventListener("keydown", onKey);
    window.clearTimeout(safety);
    splash.remove();
    root?.removeAttribute("inert");
    document.getElementById("main")?.focus({ preventScroll: true });
  };
  const leave = () => splash.classList.add("is-leaving");
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Escape") leave();
  };
  const safety = window.setTimeout(finish, SAFETY_MS); // if an animation never reports its end, the app still opens

  splash.addEventListener("click", leave); // the Skip button, or anywhere on the screen
  splash.addEventListener("animationend", (event) => {
    if (event.target === splash && (event.animationName === "splash-out" || event.animationName === "splash-leave")) finish();
  });
  window.addEventListener("keydown", onKey);
}
