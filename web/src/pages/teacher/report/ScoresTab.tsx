import { Empty } from "../../../components/States";
import { Meter } from "../../../components/Meter";
import { StateGlyph } from "../../../components/Status";
import { STATE_LABEL } from "../../../format";
import type { ReportConcept, Scores } from "../../../types";

/** Every student's score, best first, next to a shape for each concept. */
export function ScoresTab({ scores, concepts }: { scores: Scores; concepts: ReportConcept[] }) {
  if (scores.students.length === 0) {
    return <Empty title="No scores to show">Nobody matches the filters above yet.</Empty>;
  }
  return (
    <div className="tabpanel">
      {scores.average !== null ? (
        <dl className="stats">
          <div><dt>Class average</dt><dd className="figure">{scores.average}%</dd></div>
          <div><dt>Highest</dt><dd className="figure">{scores.best}%</dd></div>
          <div><dt>Lowest</dt><dd className="figure">{scores.lowest}%</dd></div>
        </dl>
      ) : null}
      <p className="note">
        A score counts the answers credited as right among the main questions, the same ones for every student. A right answer with a reason
        that shows a misunderstanding is not credited.
      </p>
      <div className="table-wrap" role="region" aria-label="Scores table" tabIndex={0}>
        <table className="table table--scores">
          <caption className="visually-hidden">Every student’s score and the state of each concept, best score first</caption>
          <thead>
            <tr>
              <th scope="col">Student</th>
              <th scope="col" className="num">Score</th>
              <th scope="col">Percent</th>
              {concepts.map((c) => <th key={c.id} scope="col" className="state-col"><span>{c.name}</span></th>)}
            </tr>
          </thead>
          <tbody>
            {scores.students.map((r, i) => (
              <tr key={`${r.nickname}-${i}`}>
                <th scope="row">
                  {r.nickname}
                  {r.simulated ? <span className="tag">Test student</span> : null}
                  {!r.finished ? <span className="tag">In progress</span> : null}
                </th>
                <td className="num figure">{r.credited} / {r.asked}</td>
                <td>
                  {r.percent === null ? "None" : (
                    <div className="cellbar">
                      <Meter value={r.percent} label={`${r.nickname}’s score`} />
                      <span className="figure">{r.percent}%</span>
                    </div>
                  )}
                </td>
                {concepts.map((c) => {
                  const state = r.states[c.id];
                  return (
                    <td key={c.id} className="state-cell">
                      {state ? <><StateGlyph state={state} /><span className="visually-hidden">{STATE_LABEL[state]}</span></> : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">Check = understood, half-filled = shaky, cross = missing.</p>
    </div>
  );
}
