import type { ReactNode } from "react";

export type IconName =
  | "check" | "cross" | "copy" | "upload" | "download" | "trash" | "lock" | "unlock" | "sun" | "moon" | "monitor" | "refresh"
  | "plus" | "file" | "alert" | "info" | "stop" | "chevron" | "logout" | "flag" | "book" | "arrow-left" | "spinner" | "play";

const line = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const ICONS: Record<IconName, ReactNode> = {
  check: <path d="M3 8.5l3.2 3.2L13 4.8" />,
  cross: <path d="M4 4l8 8M12 4l-8 8" />,
  copy: <><rect x="5.5" y="5.5" width="7" height="7" rx="1.5" /><path d="M3.5 10.5v-6a1 1 0 011-1h6" /></>,
  upload: <path d="M8 11V3m0 0L5 6m3-3l3 3M3 13h10" />,
  download: <path d="M8 3v8m0 0L5 8m3 3l3-3M3 13h10" />,
  trash: <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5M7 7v3.5M9 7v3.5" />,
  lock: <><rect x="3.75" y="7.25" width="8.5" height="6" rx="1.5" /><path d="M5.5 7.25V5.5a2.5 2.5 0 015 0v1.75" /></>,
  unlock: <><rect x="3.75" y="7.25" width="8.5" height="6" rx="1.5" /><path d="M5.5 7.25V5.5a2.5 2.5 0 014.8-1" /></>,
  sun: <><circle cx="8" cy="8" r="2.6" /><path d="M8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14M3.8 3.8l1 1M11.2 11.2l1 1M12.2 3.8l-1 1M4.8 11.2l-1 1" /></>,
  moon: <path d="M13 9.6A5.4 5.4 0 016.4 3 5.4 5.4 0 108 13.4a5.4 5.4 0 005-3.8z" />,
  monitor: <><rect x="2.25" y="3" width="11.5" height="7.5" rx="1.5" /><path d="M6 13.25h4M8 10.5v2.75" /></>,
  refresh: <path d="M13 8a5 5 0 01-8.7 3.4M3 8a5 5 0 018.7-3.4M11.7 2.5v2.1H9.6M4.3 13.5v-2.1h2.1" />,
  plus: <path d="M8 3v10M3 8h10" />,
  file: <path d="M4.5 2.5h4.8l2.7 2.7v8.3h-7.5zM9.2 2.5v2.8H12" />,
  alert: <path d="M8 2.8l5.5 9.7h-11zM8 6.8v2.6M8 11.1v.1" />,
  info: <><circle cx="8" cy="8" r="5.6" /><path d="M8 7.3v3.4M8 5.3v.1" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.2" />,
  chevron: <path d="M6 3.5L10.5 8 6 12.5" />,
  logout: <path d="M6.5 3h-3v10h3M9 5.5L11.5 8 9 10.5M11.5 8H6" />,
  flag: <path d="M4 13.5v-11M4 3h7l-1.6 2.6L11 8.2H4" />,
  book: <path d="M3 3.5h3.6a1.4 1.4 0 011.4 1.4v7.6a1.2 1.2 0 00-1.2-1.2H3zM13 3.5H9.4A1.4 1.4 0 008 4.9v7.6a1.2 1.2 0 011.2-1.2H13z" />,
  "arrow-left": <path d="M13 8H3m0 0l4-4M3 8l4 4" />,
  spinner: <path d="M8 2.5a5.5 5.5 0 105.5 5.5" />,
  play: <path d="M5 3.5l7 4.5-7 4.5z" />,
};

/** A 16px line icon. Always decorative: the words next to it (or an aria-label on the button) carry the meaning. */
export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={className ? `icon ${className}` : "icon"} viewBox="0 0 16 16" width={size} height={size} aria-hidden="true" focusable="false" {...line}>
      {ICONS[name]}
    </svg>
  );
}
