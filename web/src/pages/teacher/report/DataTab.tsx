import { useState, type FormEvent } from "react";
import { api, ApiError } from "../../../api";
import { Button, ConfirmButton, DownloadLink, Field } from "../../../components/Controls";
import { Callout, Empty } from "../../../components/States";
import type { Exam, SystemInfo } from "../../../types";

interface Props {
  exam: Exam;
  system: SystemInfo | undefined;
  buildReport: string | null;
  onChanged: () => void;
}

/** What is stored, the answers as a CSV file, test students, and how the quiz was built. */
export function DataTab({ exam, system, buildReport, onChanged }: Props) {
  const [count, setCount] = useState("14");
  const [seed, setSeed] = useState("7");
  const [busy, setBusy] = useState<"add" | "remove" | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    const n = Number(count);
    const s = Number(seed);
    if (!Number.isInteger(n) || n < 1 || n > 60 || !Number.isInteger(s) || s < 0 || s > 9999) {
      setMessage({ tone: "error", text: "Choose 1 to 60 students and a seed from 0 to 9999." });
      return;
    }
    setBusy("add");
    setMessage(null);
    try {
      const out = await api.simulate(exam.code, n, s);
      setMessage({ tone: "ok", text: `Added ${out.added} test students. They are marked as test students everywhere.` });
      onChanged();
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "Something went wrong." });
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("remove");
    setMessage(null);
    try {
      const out = await api.removeSimulated(exam.code);
      setMessage({ tone: "ok", text: `Removed ${out.removed} test students.` });
      onChanged();
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "Something went wrong." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="tabpanel datatab">
      <section aria-labelledby="stored-title">
        <h3 id="stored-title">Stored on this computer</h3>
        {system ? (
          <dl className="stats">
            {(["students", "answers", "judgements", "mastery_log"] as const).map((k) => (
              <div key={k}><dt>{k === "mastery_log" ? "mastery steps" : k}</dt><dd className="figure">{system.counts[k] ?? 0}</dd></div>
            ))}
          </dl>
        ) : null}
        <p className="note">One database holds every student and every answer, for all exams.</p>
        <DownloadLink href={api.csvUrl(exam.code)}>Download this exam’s answers (CSV)</DownloadLink>
      </section>

      <section aria-labelledby="test-title">
        <h3 id="test-title">Test students</h3>
        <p className="note">Make a class of pretend students to try the report before real students take the exam. They are always labelled and can be filtered out.</p>
        <form className="simform" onSubmit={add} noValidate>
          <Field label="How many">
            {(control) => <input {...control} className="input input--short figure" type="number" min={1} max={60} value={count} onChange={(e) => setCount(e.target.value)} />}
          </Field>
          <Field label="Random seed" hint="The same seed makes the same class.">
            {(control) => <input {...control} className="input input--short figure" type="number" min={0} max={9999} value={seed} onChange={(e) => setSeed(e.target.value)} />}
          </Field>
          <Button type="submit" busy={busy === "add"} icon="plus">Add test students</Button>
        </form>
        {exam.simulated ? (
          <ConfirmButton
            label="Remove test students"
            question={`Remove the ${exam.simulated} test students of this exam?`}
            confirmLabel="Yes, remove"
            busy={busy === "remove"}
            onConfirm={() => void remove()}
          />
        ) : null}
        {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}
      </section>

      <section aria-labelledby="build-title">
        <h3 id="build-title">How the quiz was built</h3>
        {buildReport ? (
          <pre className="buildreport" tabIndex={0}>{buildReport}</pre>
        ) : (
          <Empty title="No build report">This quiz was written by hand, not by the automatic pipeline.</Empty>
        )}
      </section>
    </div>
  );
}
