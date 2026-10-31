import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../api";
import { Button, ButtonLink, ConfirmButton, CopyButton } from "../../components/Controls";
import { Meter } from "../../components/Meter";
import { Callout } from "../../components/States";
import { ExamStatusPill } from "../../components/Status";
import { shortDate, studentLink } from "../../format";
import type { Exam } from "../../types";

interface Props {
  exam: Exam;
  linkBase: string;
  onChanged: () => void;
}

/** One exam in the list: its code, who has joined, its link, and what the teacher can do next. */
export function ExamRow({ exam, linkBase, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const link = studentLink(linkBase, exam.code);
  const open = exam.status === "ready" || exam.status === "closed";

  async function act(name: string, run: () => Promise<unknown>) {
    setBusy(name);
    setError(null);
    try {
      await run();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="exam" aria-labelledby={titleId} data-status={exam.status}>
      <header className="exam__head">
        <div>
          <h3 id={titleId} className="exam__title">
            {open ? <Link to={`/teacher/exams/${exam.code}`}>{exam.title}</Link> : exam.title}
          </h3>
          <p className="exam__meta">
            <span>Code <span className="code">{exam.code}</span></span>
            {exam.pdf_name ? <span>{exam.pdf_name}</span> : null}
            <span>Made {shortDate(exam.created_at)}</span>
          </p>
        </div>
        <ExamStatusPill status={exam.status} />
      </header>

      {exam.status === "building" ? (
        <div className="exam__build">
          <Meter value={(exam.progress ?? 0) * 100} label="Quiz build progress" />
          <p className="exam__message">{exam.message ?? "Starting."} <span className="figure">{Math.round((exam.progress ?? 0) * 100)}%</span></p>
          <p className="exam__hint">This takes several minutes. You can leave this page.</p>
          <Button small icon="stop" busy={busy === "stop"} onClick={() => void act("stop", () => api.examAction(exam.code, "stop"))}>Stop building</Button>
        </div>
      ) : null}

      {exam.status === "failed" ? (
        <div className="exam__build">
          <Callout tone="error" title="The quiz could not be built">{exam.error ?? "Something went wrong while building."}</Callout>
          <Button small variant="primary" icon="refresh" busy={busy === "retry"} onClick={() => void act("retry", () => api.examAction(exam.code, "retry"))}>Try again</Button>
        </div>
      ) : null}

      {open ? (
        <>
          <dl className="exam__facts">
            <div>
              <dt>Joined</dt>
              <dd><span className="figure">{exam.joined} of {exam.max_students}</span><Meter value={exam.joined} max={exam.max_students} label="Seats used" /></dd>
            </div>
            <div>
              <dt>Finished</dt>
              <dd><span className="figure">{exam.finished}</span></dd>
            </div>
            {exam.simulated ? (
              <div>
                <dt>Test students</dt>
                <dd><span className="figure">{exam.simulated}</span></dd>
              </div>
            ) : null}
          </dl>

          <div className="exam__link">
            <label className="field__label" htmlFor={`${titleId}-link`}>
              {exam.status === "closed" ? "Student link (closed, nobody new can join)" : "Student link"}
            </label>
            <div className="linkrow">
              <input id={`${titleId}-link`} className="input input--link" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
              <CopyButton text={link} />
            </div>
          </div>
        </>
      ) : null}

      {error ? <Callout tone="error">{error}</Callout> : null}

      {exam.status !== "building" ? (
        <footer className="exam__actions">
          {open ? <ButtonLink to={`/teacher/exams/${exam.code}`} variant="primary">Open class report</ButtonLink> : null}
          {exam.status === "ready" ? (
            <Button icon="lock" busy={busy === "close"} onClick={() => void act("close", () => api.examAction(exam.code, "close"))}>Close to new students</Button>
          ) : null}
          {exam.status === "closed" ? (
            <Button icon="unlock" busy={busy === "reopen"} onClick={() => void act("reopen", () => api.examAction(exam.code, "reopen"))}>Reopen</Button>
          ) : null}
          <ConfirmButton
            label="Delete"
            question={exam.joined || exam.simulated ? "Delete this exam and its students’ answers?" : "Delete this exam?"}
            confirmLabel="Yes, delete"
            busy={busy === "delete"}
            onConfirm={() => void act("delete", () => api.deleteExam(exam.code))}
          />
        </footer>
      ) : null}
    </article>
  );
}
