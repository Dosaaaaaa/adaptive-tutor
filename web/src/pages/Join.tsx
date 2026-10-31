import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Button, ButtonLink, Field } from "../components/Controls";
import { StudentShell } from "../components/Shell";
import { Callout, ErrorBlock, Loading } from "../components/States";
import { MIN_REASON_WORDS, normalizeCode } from "../format";
import { rememberSession, savedSession, useResource, useTitle } from "../hooks";

/** The page behind the link the teacher shares: pick a nickname and start. */
export default function Join() {
  const code = normalizeCode(useParams().code ?? "");
  const exam = useResource((signal) => api.publicExam(code, signal), [code]);
  useTitle(exam.data?.title ?? "Join your exam");

  return (
    <StudentShell>
      {exam.loading ? (
        <Loading label="Finding your exam" />
      ) : exam.error ? (
        <>
          <ErrorBlock
            error={exam.error}
            level={1}
            title={exam.error.status === 404 ? "No exam with that code" : "That did not load"}
            onRetry={exam.error.status === 404 ? undefined : exam.reload}
          />
          <p className="after"><Link to="/">Type a different code</Link></p>
        </>
      ) : exam.data ? (
        <section aria-labelledby="exam-title">
          <h1 id="exam-title">{exam.data.title}</h1>
          {exam.data.can_join ? (
            <>
              <ol className="steps">
                <li>Answer up to three short rounds of multiple-choice questions.</li>
                <li>For every answer, write one or two sentences on why you chose it. Use at least {MIN_REASON_WORDS} words, or tick “I am guessing”.</li>
                <li>You find out which answers were right at the very end, together with your score.</li>
              </ol>
              <JoinForm code={exam.data.code} />
            </>
          ) : (
            <Callout tone="warn" title="You cannot join yet">{exam.data.message ?? "This exam is not open."}</Callout>
          )}
        </section>
      ) : null}
    </StudentShell>
  );
}

function JoinForm({ code }: { code: string }) {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const saved = savedSession(code);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const name = nickname.trim();
    if (!name) {
      setError("Type a nickname. It does not have to be your real name.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const joined = await api.join(code, name);
      rememberSession(code, joined.token);
      navigate(`/play/${joined.token}`, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <>
      {saved ? (
        <div className="resume">
          <Callout tone="info" title="You already started this exam on this page">
            Carry on where you stopped, or start again with a new nickname below.
          </Callout>
          <ButtonLink to={`/play/${saved}`} variant="primary" icon="play">Carry on</ButtonLink>
        </div>
      ) : null}
      <form className="join" onSubmit={submit} noValidate>
        <Field label="Your nickname" hint="Not your real name. Your teacher sees it next to your results." error={error}>
          {(control) => (
            <input
              {...control}
              className="input"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              maxLength={30}
              autoComplete="nickname"
              spellCheck={false}
            />
          )}
        </Field>
        <Button type="submit" variant="primary" busy={busy}>{busy ? "Starting…" : "Start the exam"}</Button>
      </form>
    </>
  );
}
