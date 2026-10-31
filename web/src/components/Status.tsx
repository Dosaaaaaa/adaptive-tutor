import { STATE_LABEL } from "../format";
import type { ExamStatus, MasteryState } from "../types";
import { Icon } from "./Icon";

/** The shape of a concept's state. The shape differs as well as the colour, so it reads without colour. */
export function StateGlyph({ state, size = 16 }: { state: MasteryState; size?: number }) {
  return (
    <svg className="glyph" data-state={state} viewBox="0 0 16 16" width={size} height={size} aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      {state === "understood" && <path d="M5 8.3l2 2 4-4.4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />}
      {state === "shaky" && <path d="M8 1.75a6.25 6.25 0 010 12.5z" fill="currentColor" />}
      {state === "missing" && <path d="M5.7 5.7l4.6 4.6M10.3 5.7l-4.6 4.6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />}
    </svg>
  );
}

export function StatePill({ state, label }: { state: MasteryState; label?: string }) {
  return (
    <span className="pill" data-tone={state}>
      <StateGlyph state={state} size={14} />
      {label ?? STATE_LABEL[state]}
    </span>
  );
}

const EXAM_STATUS: Record<ExamStatus, { label: string; tone: string }> = {
  building: { label: "Being prepared", tone: "working" },
  ready: { label: "Open", tone: "understood" },
  closed: { label: "Closed", tone: "neutral" },
  failed: { label: "Failed", tone: "missing" },
};

export function ExamStatusPill({ status }: { status: ExamStatus }) {
  const { label, tone } = EXAM_STATUS[status];
  return (
    <span className="pill" data-tone={tone}>
      {status === "building" && <Icon name="spinner" size={14} className="icon--spin" />}
      {status === "ready" && <Icon name="check" size={14} />}
      {status === "closed" && <Icon name="lock" size={14} />}
      {status === "failed" && <Icon name="cross" size={14} />}
      {label}
    </span>
  );
}
