import type { ReactNode } from "react";
import type { ApiError } from "../api";
import { Button } from "./Controls";
import { Icon } from "./Icon";

/** Grey blocks where the content will be. They keep the page from jumping when the data arrives. */
export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="loading" role="status" aria-live="polite" aria-busy="true">
      <span className="visually-hidden">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="loading__bar" style={{ width: `${88 - i * 14}%` }} />
      ))}
    </div>
  );
}

/** A heading at the level the page needs: a screen whose only content is an error still needs its own h1. */
function Title({ level, children }: { level: 1 | 2 | 3; children: ReactNode }) {
  const Tag = `h${level}` as const;
  return <Tag className="state__title">{children}</Tag>;
}

export function ErrorBlock({ error, title = "That did not load", onRetry, level = 3 }: { error: ApiError | Error; title?: string; onRetry?: () => void; level?: 1 | 2 | 3 }) {
  return (
    <div className="state state--error" role="alert">
      <Icon name="alert" size={20} />
      <div className="state__body">
        <Title level={level}>{title}</Title>
        <p>{error.message}</p>
        {onRetry ? <Button small icon="refresh" onClick={onRetry}>Try again</Button> : null}
      </div>
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state state--empty">
      <div className="state__body">
        <Title level={3}>{title}</Title>
        {children ? <p>{children}</p> : null}
        {action}
      </div>
    </div>
  );
}

type Tone = "info" | "warn" | "error" | "ok";

/** A message that stays in the page. Errors interrupt a screen reader, everything else waits its turn. */
export function Callout({ tone = "info", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  const icon = tone === "ok" ? "check" : tone === "info" ? "info" : "alert";
  return (
    <div className="callout" data-tone={tone} role={tone === "error" ? "alert" : "status"}>
      <Icon name={icon} />
      <div className="callout__body">
        {title ? <strong>{title}</strong> : null}
        <span>{children}</span>
      </div>
    </div>
  );
}
