import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Button } from "../components/Controls";
import { Icon } from "../components/Icon";
import { Meter } from "../components/Meter";
import { StudentShell } from "../components/Shell";
import { Callout, ErrorBlock, Loading } from "../components/States";
import { MIN_REASON_WORDS, wordCount } from "../format";
import { useTitle } from "../hooks";
import type { AnswerBody, PlayQuestion, PlayState } from "../types";

/** The exam itself: one question at a time, each with a reason, until the last round is checked. */
export default function Play() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState<PlayState | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [judgeError, setJudgeError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);
  useTitle(state ? state.exam.title : "Your exam");

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    api.play(token, controller.signal).then(setState).catch((err) => {
      if (!(err instanceof DOMException)) setLoadError(err instanceof ApiError ? err : new ApiError(0, "Something went wrong."));
    });
    return () => controller.abort();
  }, [token, attempt]);

  // A round has just ended: ask the server to check the reasons, which can take a few seconds when an AI is used.
  const phase = state?.phase;
  useEffect(() => {
    if (phase !== "judging") return;
    let alive = true;
    setJudgeError(null);
    api.finish(token).then((next) => alive && setState(next)).catch((err) => {
      if (alive) setJudgeError(err instanceof ApiError ? err : new ApiError(0, "Something went wrong."));
    });
    return () => { alive = false; };
  }, [phase, token, attempt]);

  useEffect(() => {
    if (phase === "done") navigate(`/play/${token}/results`, { replace: true });
  }, [phase, token, navigate]);

  async function submit(body: AnswerBody) {
    setSaving(true);
    setSaveError(null);
    try {
      setState(await api.answer(token, body));
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <StudentShell>
      {loadError ? (
        <>
          <ErrorBlock
            error={loadError}
            level={1}
            title={loadError.status === 404 ? "We could not find this exam session" : "That did not load"}
            onRetry={loadError.status === 404 ? undefined : () => setAttempt((n) => n + 1)}
          />
          <p className="after"><Link to="/">Back to the start</Link></p>
        </>
      ) : !state ? (
        <Loading label="Opening your exam" />
      ) : state.phase === "question" && state.question ? (
        <QuestionCard key={state.question.id} q={state.question} busy={saving} error={saveError} onSubmit={submit} />
      ) : judgeError ? (
        <ErrorBlock error={judgeError} level={1} title="We could not check your answers yet" onRetry={() => setAttempt((n) => n + 1)} />
      ) : (
        <Judging />
      )}
    </StudentShell>
  );
}

function Judging() {
  return (
    <section className="judging" role="status" aria-live="polite">
      <h1>Checking your reasoning</h1>
      <div className="meter meter--wait" aria-hidden="true"><span className="meter__fill" /></div>
      <p>This takes a few seconds. Please keep this page open.</p>
    </section>
  );
}

interface CardProps {
  q: PlayQuestion;
  busy: boolean;
  error: string | null;
  onSubmit: (body: AnswerBody) => void;
}

function QuestionCard({ q, busy, error, onSubmit }: CardProps) {
  const [choice, setChoice] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [guess, setGuess] = useState(false);
  const [problem, setProblem] = useState<{ field: "choice" | "reason"; text: string } | null>(null);
  const shownAt = useRef(Date.now());
  const stemRef = useRef<HTMLHeadingElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const groupRef = useRef<HTMLDivElement>(null);
  const stemId = useId();
  const reasonId = useId();
  const countId = useId();
  const words = wordCount(reason);
  const enough = words >= MIN_REASON_WORDS;

  // Each new question starts at the top and is announced by moving focus to it.
  useEffect(() => {
    stemRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!choice) {
      setProblem({ field: "choice", text: "Pick an answer first." });
      groupRef.current?.querySelector<HTMLInputElement>("input")?.focus();
      return;
    }
    if (!guess && !enough) {
      setProblem({ field: "reason", text: `Explain your choice in at least ${MIN_REASON_WORDS} words, or tick “I am guessing”.` });
      reasonRef.current?.focus();
      return;
    }
    setProblem(null);
    onSubmit({
      question_id: q.id,
      choice,
      reason: reason.trim(),
      is_guess: guess,
      seconds: Math.round((Date.now() - shownAt.current) / 100) / 10,
    });
  }

  return (
    <form className="question" onSubmit={submit} noValidate>
      <header className="question__head">
        <p className="question__round">Round {q.round} of 3</p>
        <p className="question__count figure">Question {q.index} of {q.total}</p>
        <Meter value={q.index - 1} max={q.total} label="Progress through this round" tone="person" />
      </header>

      <h1 className="question__stem" id={stemId} ref={stemRef} tabIndex={-1}>{q.stem}</h1>

      <div className="options" role="radiogroup" aria-labelledby={stemId} aria-describedby={problem?.field === "choice" ? "choice-problem" : undefined} ref={groupRef}>
        {q.options.map((o) => (
          <label key={o.key} className="choice" data-checked={choice === o.key ? "true" : undefined}>
            <input
              type="radio"
              name="answer"
              value={o.key}
              checked={choice === o.key}
              onChange={() => { setChoice(o.key); if (problem?.field === "choice") setProblem(null); }}
            />
            <span className="choice__letter" aria-hidden="true">{o.label}</span>
            <span className="choice__text">{o.text}</span>
          </label>
        ))}
      </div>
      {problem?.field === "choice" ? <p className="field__error" id="choice-problem" role="alert"><Icon name="alert" size={14} />{problem.text}</p> : null}

      <div className="field" data-invalid={problem?.field === "reason" ? "true" : undefined}>
        <label className="field__label" htmlFor={reasonId}>Why did you pick this?</label>
        <p className="field__hint">Write one or two sentences in your own words.</p>
        <textarea
          id={reasonId}
          ref={reasonRef}
          className="textarea"
          rows={3}
          maxLength={1500}
          value={reason}
          onChange={(e) => { setReason(e.target.value); if (problem?.field === "reason") setProblem(null); }}
          aria-describedby={countId}
          aria-invalid={problem?.field === "reason" ? true : undefined}
          placeholder="I chose this because…"
        />
        <p className="count figure" id={countId} data-met={guess || enough ? "true" : undefined}>
          {guess ? "You do not need a reason for a guess." : enough ? <><Icon name="check" size={14} />{words} words. That is enough.</> : `${words} of ${MIN_REASON_WORDS} words`}
        </p>
        {problem?.field === "reason" ? <p className="field__error" role="alert"><Icon name="alert" size={14} />{problem.text}</p> : null}
      </div>

      <label className="check">
        <input type="checkbox" checked={guess} onChange={(e) => { setGuess(e.target.checked); setProblem(null); }} />
        <span>I am guessing</span>
      </label>

      {error ? <Callout tone="error" title="Your answer was not saved">{error}</Callout> : null}

      <div className="question__actions">
        <Button type="submit" variant="primary" busy={busy}>{busy ? "Saving…" : "Submit answer"}</Button>
        <p className="question__note">Your place is saved. You can close this page and open the same link again.</p>
      </div>
    </form>
  );
}
