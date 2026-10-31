import { Icon } from "../../../components/Icon";
import { StatePill } from "../../../components/Status";
import { CLASS_STATE } from "../../../format";
import type { ReportConcept } from "../../../types";

/** The first thing a teacher reads: the few concepts to teach again, in the order to do it. */
export function Reteach({ cards }: { cards: ReportConcept[] }) {
  return (
    <section className="reteach" aria-labelledby="reteach-title">
      <h2 id="reteach-title">Re-teach these first</h2>
      {cards.length === 0 ? (
        <p className="reteach__none">No concept needs re-teaching. Most of the class understood every concept.</p>
      ) : (
        <ol className="reteach__list">
          {cards.map((c, i) => (
            <li key={c.id} className="reteach__card">
              <header>
                <span className="reteach__rank figure" aria-hidden="true">{i + 1}</span>
                <h3>{c.name}</h3>
                <StatePill state={CLASS_STATE[c.status]} label={c.status_label} />
              </header>
              <p className="reteach__headline">{c.headline}.</p>
              {c.start_here ? (
                <p className="reteach__start"><Icon name="flag" /><span><strong>Start here.</strong> This is the first gap for {c.root_count} of {c.n} students.</span></p>
              ) : null}
              {c.top_mistake ? (
                <p>Most common mistake: <q>{c.top_mistake.statement}</q></p>
              ) : null}
              {c.top_mistake ? (
                <p className="seen">Seen in <span className="figure">{c.top_mistake.students}</span> {c.top_mistake.students === 1 ? "student" : "students"}.</p>
              ) : null}
              {c.holds_back.length ? <p>Also holds back: {c.holds_back.join(", ")}.</p> : null}
              <p className="reteach__page"><Icon name="book" />Re-read page {c.page}</p>
              {c.top_mistake?.quotes.length ? (
                <details className="quotes">
                  <summary>What students wrote</summary>
                  <ul>
                    {c.top_mistake.quotes.map((q, k) => <li key={k}><blockquote>{q}</blockquote></li>)}
                  </ul>
                </details>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
