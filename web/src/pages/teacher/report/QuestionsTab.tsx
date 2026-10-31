import { Empty } from "../../../components/States";
import { Icon } from "../../../components/Icon";
import { Meter } from "../../../components/Meter";
import { flagText, KIND_TEXT, ratioPercent } from "../../../format";
import type { QuestionStat, ReportConcept } from "../../../types";

interface Props {
  questions: QuestionStat[];
  concepts: ReportConcept[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

/** How hard each question really was, measured from the answers, and which wrong option lured students. */
export function QuestionsTab({ questions, concepts, selected, onSelect }: Props) {
  if (questions.length === 0) return <Empty title="No questions">This quiz has no questions.</Empty>;
  const nameOf = (id: string) => concepts.find((c) => c.id === id)?.name ?? id;
  const chosen = questions.find((q) => q.question_id === selected) ?? null;

  return (
    <div className="tabpanel">
      <p className="note">
        Hardest first. Difficulty is measured from the students’ answers, not guessed. Round 3 questions were only seen by students who struggled earlier.
      </p>
      <div className="table-wrap" role="region" aria-label="Questions table" tabIndex={0}>
        <table className="table table--questions">
          <caption className="visually-hidden">Every question, hardest first</caption>
          <thead>
            <tr>
              <th scope="col">Question</th>
              <th scope="col">Concept</th>
              <th scope="col">Type</th>
              <th scope="col" className="num">Right</th>
              <th scope="col">Share right</th>
              <th scope="col">Difficulty</th>
              <th scope="col">Flags</th>
            </tr>
          </thead>
          <tbody>
            {questions.map((q) => (
              <tr key={q.question_id} data-selected={q.question_id === selected ? "true" : undefined}>
                <th scope="row">
                  <button type="button" className="linklike" aria-pressed={q.question_id === selected} onClick={() => onSelect(q.question_id === selected ? null : q.question_id)}>
                    <span className="code">{q.question_id}</span>
                    <span className="clip">{q.stem}</span>
                  </button>
                </th>
                <td>{nameOf(q.concept_id)}</td>
                <td>{KIND_TEXT[q.kind] ?? q.kind}, round {q.round}</td>
                <td className="num figure">{q.k} of {q.n}</td>
                <td>
                  {q.n === 0 ? "No data" : (
                    <div className="cellbar">
                      <Meter value={ratioPercent(q.p)} label={`Share right for ${q.question_id}`} />
                      <span className="figure">{ratioPercent(q.p)}%</span>
                    </div>
                  )}
                </td>
                <td><span className="diff" data-level={q.label.toLowerCase().replace(" ", "-")}>{q.label}</span></td>
                <td>
                  {q.flags.length ? (
                    <span className="flags">{q.flags.map((f) => <span key={f} className="flag"><Icon name="flag" size={14} />{flagText(f)}</span>)}</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="detail" aria-live="polite">
        {chosen ? (
          <>
            <header className="detail__head">
              <h3>{chosen.stem}</h3>
            </header>
            <p className="note">{nameOf(chosen.concept_id)}. {chosen.n} {chosen.n === 1 ? "student" : "students"} answered.</p>
            <ul className="picks">
              {chosen.options.map((o) => {
                const right = o.tag === "correct";
                return (
                  <li key={o.key} className="pick" data-right={right ? "true" : undefined}>
                    <span className="pick__text">{o.text}</span>
                    <span className="pick__kind">{right ? <><Icon name="check" size={14} />Right answer</> : o.label}</span>
                    <span className="pick__count figure">{o.picked}</span>
                    <Meter value={o.picked} max={Math.max(1, chosen.n)} label={`Students who chose ${o.key}`} />
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <p className="detail__hint">Select a question to see how often each answer was chosen.</p>
        )}
      </div>
    </div>
  );
}
