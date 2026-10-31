// Small, pure helpers for text and numbers. Kept free of React so they are easy to test.
import type { ClassStatus, MasteryState, QuestionStat } from "./types";

/** Words the way the server counts them, so the counter on the form agrees with the check on the server. */
export function wordCount(text: string): number {
  return (text.match(/[\p{L}\p{N}_]+/gu) ?? []).length;
}

export const MIN_REASON_WORDS = 6;

/** The exam code as the server stores it: capitals and digits only. */
export function normalizeCode(text: string): string {
  return text.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 12);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function ratioPercent(value: number): number {
  return Math.round(value * 100);
}

export const STATE_LABEL: Record<MasteryState, string> = { understood: "Understood", shaky: "Shaky", missing: "Missing" };

export const CLASS_STATE: Record<ClassStatus, MasteryState> = { green: "understood", orange: "shaky", red: "missing" };

export const CLASS_LABEL: Record<ClassStatus, string> = { green: "Class has it", orange: "Shaky", red: "Missing" };

export const FLAG_TEXT: Record<string, string> = {
  check_question: "Check this question",
  too_easy: "Too easy",
  order_broken: "Easy question is harder",
};

export const KIND_TEXT: Record<string, string> = { recall: "Recall", apply: "Apply", simple: "Simple follow-up" };

export function flagText(flag: string): string {
  return FLAG_TEXT[flag] ?? flag.replace(/_/g, " ");
}

export function difficultyOrder(label: QuestionStat["label"]): number {
  return { Hard: 0, Medium: 1, Easy: 2, "No data": 3 }[label];
}

/** "31 Oct, 18:21" in the person's own time zone. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

/** The link a student opens. It is built from the server's address, so it works from another computer. */
export function studentLink(base: string, code: string): string {
  return `${base.replace(/\/+$/, "")}/e/${code}`;
}

/** Splits a long name into at most `maxLines` lines of about `maxChars` letters, for the labels inside the concept map. */
export function wrapLabel(text: string, maxChars: number, maxLines: number): string[] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length <= maxChars || !line) {
      line = next;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  const last = kept[maxLines - 1] ?? "";
  kept[maxLines - 1] = `${last.slice(0, Math.max(1, maxChars - 1)).trimEnd()}…`;
  return kept;
}

/** Where to go after signing in. Only pages of the teacher area are allowed, so a crafted link cannot send anyone elsewhere. */
export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/teacher") || value.startsWith("//") || value.includes("\\")) return "/teacher";
  return value;
}
