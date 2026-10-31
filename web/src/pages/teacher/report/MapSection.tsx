import { useMemo } from "react";
import { Button } from "../../../components/Controls";
import { ConceptMap } from "../../../components/ConceptMap";
import { Icon } from "../../../components/Icon";
import { StatePill } from "../../../components/Status";
import { CLASS_STATE } from "../../../format";
import type { ClassReport, ReportConcept } from "../../../types";

interface Props {
  report: ClassReport;
  selected: string | null;
  onSelect: (id: string | null) => void;
}

/** The concept map with the details of whichever concept is chosen, and the same facts as a table for those who prefer one. */
export function MapSection({ report, selected, onSelect }: Props) {
  const startHere = useMemo(() => new Set(report.concepts.filter((c) => c.start_here).map((c) => c.id)), [report.concepts]);
  const chosen = report.concepts.find((c) => c.id === selected) ?? null;
  const nameOf = (id: string) => report.concepts.find((c) => c.id === id)?.name ?? id;

  return (
    <section className="mapsection" aria-labelledby="map-title">
      <h2 id="map-title">Concept map</h2>
      <p className="mapsection__lead">Read from left to right: concepts on the left come first. Select a concept to see who is stuck and why.</p>
      <ConceptMap nodes={report.graph.nodes} edges={report.graph.edges} startHere={startHere} selected={selected} onSelect={onSelect} />

      <div className="detail" aria-live="polite">
        {chosen ? <Detail concept={chosen} nameOf={nameOf} onClear={() => onSelect(null)} /> : <p className="detail__hint">No concept selected.</p>}
      </div>

      <details className="astable">
        <summary>Show the concepts as a table</summary>
        <div className="table-wrap" role="region" aria-label="Concepts table" tabIndex={0}>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Concept</th>
                <th scope="col">Class status</th>
                <th scope="col" className="num">Understood</th>
                <th scope="col" className="num">Shaky</th>
                <th scope="col" className="num">Missing</th>
                <th scope="col">Learn first</th>
              </tr>
            </thead>
            <tbody>
              {report.concepts.map((c) => (
                <tr key={c.id}>
                  <th scope="row">{c.name}</th>
                  <td><StatePill state={CLASS_STATE[c.status]} label={c.status_label} /></td>
                  <td className="num figure">{c.understood}</td>
                  <td className="num figure">{c.shaky}</td>
                  <td className="num figure">{c.missing}</td>
                  <td>{c.parents.length ? c.parents.map(nameOf).join(", ") : "Nothing"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function Detail({ concept: c, nameOf, onClear }: { concept: ReportConcept; nameOf: (id: string) => string; onClear: () => void }) {
  return (
    <>
      <header className="detail__head">
        <h3>{c.name}</h3>
        <StatePill state={CLASS_STATE[c.status]} label={c.status_label} />
        <Button small onClick={onClear}>Clear</Button>
      </header>
      <dl className="detail__counts">
        <div><dt>Understood</dt><dd className="figure">{c.understood}</dd></div>
        <div><dt>Shaky</dt><dd className="figure">{c.shaky}</dd></div>
        <div><dt>Missing</dt><dd className="figure">{c.missing}</dd></div>
      </dl>
      {c.start_here ? <p className="detail__start"><Icon name="flag" /><span><strong>Start here.</strong> This is the first gap for {c.root_count} of {c.n} students.</span></p> : null}
      {c.parents.length ? <p>Learn first: {c.parents.map(nameOf).join(", ")}.</p> : <p>This concept has no prerequisite.</p>}
      {c.holds_back.length ? <p>Still holds back: {c.holds_back.join(", ")}.</p> : null}
      {c.top_mistake ? (
        <>
          <p>Most common mistake: <q>{c.top_mistake.statement}</q></p>
          <p className="seen">Seen in <span className="figure">{c.top_mistake.students}</span> {c.top_mistake.students === 1 ? "student" : "students"}.</p>
        </>
      ) : (
        <p>No common mistake has been recorded for this concept yet.</p>
      )}
      <p className="reteach__page"><Icon name="book" />Re-read page {c.page}</p>
    </>
  );
}
