import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, UNAUTHORIZED_EVENT } from "./api";

export interface Resource<T> {
  data: T | undefined;
  error: ApiError | null;
  /** True until the first answer (or error) arrives. */
  loading: boolean;
  /** True while a later refresh is under way; the old data stays on screen meanwhile. */
  refreshing: boolean;
  /** When the data on screen was fetched (milliseconds since 1970), or null before the first answer. */
  updatedAt: number | null;
  reload: () => void;
}

/**
 * Loads data and keeps it fresh. `poll` returns how many milliseconds to wait before the next load, or null to stop.
 * Polling pauses while the tab is hidden and catches up when it is shown again.
 */
export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  poll?: (data: T | undefined) => number | null,
): Resource<T> {
  const [state, setState] = useState<{ data: T | undefined; error: ApiError | null; loading: boolean; refreshing: boolean; updatedAt: number | null }>({
    data: undefined, error: null, loading: true, refreshing: false, updatedAt: null,
  });
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  const pollRef = useRef(poll);
  loadRef.current = load;
  pollRef.current = poll;

  useEffect(() => {
    const controller = new AbortController();
    let alive = true;
    let timer: number | undefined;
    let waitingForTab = false;
    let last: T | undefined;

    const run = async (first: boolean) => {
      if (!first) setState((s) => ({ ...s, refreshing: true }));
      try {
        last = await loadRef.current(controller.signal);
        if (!alive) return;
        setState({ data: last, error: null, loading: false, refreshing: false, updatedAt: Date.now() });
      } catch (err) {
        if (!alive || (err instanceof DOMException && err.name === "AbortError")) return;
        const error = err instanceof ApiError ? err : new ApiError(0, "Something went wrong. Please try again.");
        setState((s) => ({ ...s, error, loading: false, refreshing: false }));
      }
      const wait = pollRef.current?.(last) ?? null;      // after a failed refresh the last good data still decides
      if (alive && wait) timer = window.setTimeout(() => void again(), wait);
    };

    const again = async () => {
      if (document.hidden) {
        waitingForTab = true;
        return;
      }
      await run(false);
    };

    const onVisible = () => {
      if (!document.hidden && waitingForTab && alive) {
        waitingForTab = false;
        void run(false);
      }
    };

    document.addEventListener("visibilitychange", onVisible);
    void run(true);
    return () => {
      alive = false;
      controller.abort();
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

export function useTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} – Adaptive Tutor`;
  }, [title]);
}

/** Sends the teacher to the sign-in page when any request finds the session has ended. */
export function useOnUnauthorized(handler: () => void): void {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const listener = () => ref.current();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  }, []);
}

// ---- colour mode ----

export type Mode = "system" | "light" | "dark";
const MODE_KEY = "tutor-mode";

export function readMode(): Mode {
  try {
    const saved = localStorage.getItem(MODE_KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

export function applyMode(mode: Mode): void {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-mode");
  else root.setAttribute("data-mode", mode);
  try {
    if (mode === "system") localStorage.removeItem(MODE_KEY);
    else localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* the choice still applies for this visit */
  }
}

export function useMode(): readonly [Mode, (mode: Mode) => void] {
  const [mode, setMode] = useState<Mode>(readMode);
  const change = useCallback((next: Mode) => {
    applyMode(next);
    setMode(next);
  }, []);
  return [mode, change] as const;
}

// ---- the student's place ----

const tokenKey = (code: string) => `tutor-session-${code}`;

/** The student's session lives in this tab only, so the next person at a shared computer starts fresh. */
export function rememberSession(code: string, token: string): void {
  try {
    sessionStorage.setItem(tokenKey(code), token);
  } catch {
    /* the link in the address bar still carries the place */
  }
}

export function savedSession(code: string): string | null {
  try {
    return sessionStorage.getItem(tokenKey(code));
  } catch {
    return null;
  }
}

export function forgetSession(code: string): void {
  try {
    sessionStorage.removeItem(tokenKey(code));
  } catch {
    /* nothing to forget */
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}
