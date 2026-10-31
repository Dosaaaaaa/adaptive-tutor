import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Callout, ErrorBlock, Loading } from "../components/States";
import { StatePill } from "../components/Status";
import { StudentShell } from "../components/Shell";
import { Icon } from "../components/Icon";
import { useResource, useTitle } from "../hooks";
import type { ResultsOut } from "../types";

/** The end of the exam: the score, where to read again, and what each missed answer showed. */
export default function Results() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const res = useResource((signal) => api.results(token, signal), [token]);
  useTitle("Your results");

  // Someone opened the results link before finishing: send them back to their question.
  const notFinished = res.error?.status === 409;
  useEffect(() => {
    if (notFinished) navigate(`/play/${token}`, { replace: true });
  }, [notFinished, token, navigate]);

  return (
    <StudentShell>
      {res.loading || notFinished ? (
        <Loading label="Getting your results" />
      ) : res.error ? (
        <>
          <ErrorBlock error={res.error} level={1} onRetry={res.error.status === 404 ? undefined : res.reload} />
          <p className="after"><Link to="/">Back to the start</Link></p>
        </>
      ) : res.data ? (
        <Body data={res.data} />
      ) : null}
    </StudentShell>
  );
}

function Body({ data }: { data: ResultsOut }) {
  const { score } = data;
  return (
    <div className="results">
      <header>
        <h1>You are done, {data.nickname}</h1>
        <p className="lead">{data.exam.title}</p>
      </header>

      <section className="score" aria-labelledby="score-title">
        <h2 id="score-title">Your score</h2>
        {score.percent === null ? (
          <p className="score__none">There was no scored question in your exam.</p>
        ) : (
          <>
            <p className="score__figure figure">
              <span className="score__big">{score.credited}</span>
              <span className="score__of">out of {score.asked}</span>
              <span className="score__pct">{score.percent}%</span>
            </p>
            <p className="score__note">
              The score counts the main questions. A right answer with a reason that shows a misunderstanding does not count,
              and the extra follow-up questions are not part of it.
            </p>
          </>
        )}
      </section>

      <section aria-labelledby="concepts-title">
        <h2 id="concepts-title">Concept by concept</h2>
        <ul className="ladder">
          {data.concepts.map((c) => (
            <li key={c.id} className="ladder__row">
              <span className="ladder__name">{c.name}</span>
              <StatePill state={c.state} />
              {c.state !== "understood" ? <span className="ladder__read"><Icon name="book" size={14} />Read page {c.page} again</span> : <span />}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="review-title">
        <h2 id="review-title">Answers to look at again</h2>
        {data.review.length === 0 ? (
          <Callout tone="ok" title="Every answer counted">There is nothing to look at again.</Callout>
        ) : (
          <div className="reviews">
            {data.review.map((r, i) => (
              <details key={i} className="review">
                <summary>
                  <span className="review__concept">{r.concept}</span>
                  <span className="review__stem">{r.question}</span>
                  <Icon name="chevron" className="review__chev" />
                </summary>
                <dl className="review__body">
                  <div><dt>Your answer</dt><dd>{r.your_answer}</dd></div>
                  {r.was_right_choice ? <p className="review__note">Your choice was right, but your reason did not match the idea in the notes.</p> : null}
                  <div><dt>Right answer</dt><dd>{r.correct_answer}</dd></div>
                  {r.your_reason ? <div><dt>Your reason</dt><dd className="review__quote">{r.your_reason}</dd></div> : null}
                  {r.misconception ? <div><dt>The idea to fix</dt><dd>{r.misconception}</dd></div> : null}
                  <div><dt>Why</dt><dd>{r.explanation} <span className="review__page">Page {r.page} of the notes.</span></dd></div>
                </dl>
              </details>
            ))}
          </div>
        )}
      </section>

      <p className="after">Your teacher will see the results for the whole class. You can close this page now.</p>
    </div>
  );
}
