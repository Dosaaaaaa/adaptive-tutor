import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import type { Include } from "../../../types";

export type Tab = "scores" | "questions" | "mistakes" | "data";
export const TABS: { id: Tab; label: string }[] = [
  { id: "scores", label: "Scores" },
  { id: "questions", label: "Questions" },
  { id: "mistakes", label: "Mistakes" },
  { id: "data", label: "Data and build" },
];

const INCLUDES: Include[] = ["all", "real", "simulated"];

/** What the teacher is looking at, kept in the address so a reload, a bookmark or a shared link shows the same view. */
export function useReportParams() {
  const [params, setParams] = useSearchParams();
  const show = params.get("show");
  const tab = params.get("tab");
  const set = useCallback(
    (changes: Record<string, string | null>) =>
      setParams((previous) => {
        const next = new URLSearchParams(previous);
        for (const [key, value] of Object.entries(changes)) {
          if (value === null) next.delete(key);
          else next.set(key, value);
        }
        return next;
      }, { replace: true }),
    [setParams],
  );
  return {
    include: (INCLUDES.find((i) => i === show) ?? "all") as Include,
    onlyDone: params.get("done") !== "0",
    live: params.get("live") !== "0",
    tab: (TABS.find((t) => t.id === tab)?.id ?? "scores") as Tab,
    concept: params.get("concept"),
    question: params.get("q"),
    set,
    search: params.toString(),
  };
}
