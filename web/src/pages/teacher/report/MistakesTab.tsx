import { Empty } from "../../../components/States";
import type { ClassReport } from "../../../types";

/** The wrong ideas students held, with their own words as evidence. */
export function MistakesTab({ report }: { report: ClassReport }) {
  const nameOf = (id: string) => report.concepts.find((c) => c.id === id)?.name ?? id;
  if (report.mistakes.length === 0 && report.other_texts.length === 0) {
    return <Empty title="No misconceptions found yet">When a student’s reason shows a wrong idea, it appears here with what they wrote.</Empty>;
  }
  return (
    <div className="tabpanel">
      <div className="mistakes">
        {report.mistakes.map((m) => (
          <details key={m.id} className="mistake">
            <summary>
              <span className="mistake__count figure">{m.students}</span>
              <span className="mistake__what"><span className="mistake__concept">{m.concept}</span><q>{m.statement}</q></span>
            </summary>
            <ul className="quotes__list">
              {m.quotes.map((q, i) => <li key={i}><blockquote>{q}</blockquote></li>)}
            </ul>
          </details>
        ))}
      </div>
      {report.other_texts.length ? (
        <section className="other" aria-labelledby="other-title">
          <h3 id="other-title">Other wrong ideas that are not on the list</h3>
          <ul>
            {report.other_texts.map((o, i) => <li key={i}><strong>{nameOf(o.concept_id)}:</strong> {o.text}</li>)}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
