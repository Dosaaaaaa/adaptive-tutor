import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../../api";
import { Button, CopyButton, Segmented } from "../../components/Controls";
import { Icon } from "../../components/Icon";
import { Callout, Empty, ErrorBlock, Loading } from "../../components/States";
import { ExamStatusPill } from "../../components/Status";
import { normalizeCode, studentLink } from "../../format";
import { useResource, useTitle } from "../../hooks";
import type { ReportOut } from "../../types";
import { DataTab } from "./report/DataTab";
import { MapSection } from "./report/MapSection";
import { MistakesTab } from "./report/MistakesTab";
import { QuestionsTab } from "./report/QuestionsTab";
import { Reteach } from "./report/Reteach";
import { ScoresTab } from "./report/ScoresTab";
import { TABS, useReportParams } from "./report/useReportParams";

export default function Report() {
  const code = normalizeCode(useParams().code ?? "");
  return <ReportPage key={code} code={code} />;
}

function ReportPage({ code }: { code: string }) {
  const p = useReportParams();
  const system = useResource((signal) => api.system(signal), []);
  const rep = useResource(
    (signal) => api.report(code, p.include, p.onlyDone, signal),
    [code, p.include, p.onlyDone, p.live],
    () => (p.live ? 15000 : null),
  );
  useTitle(rep.data ? `${rep.data.exam.title} report` : "Class report");

  return (
    <>
      <p className="crumb"><Link to="/teacher"><Icon name="arrow-left" size={14} />All exams</Link></p>
      {rep.loading ? (
        <>
          <h1>Class report</h1>
          <Loading label="Building the class report" rows={5} />
        </>
      ) : rep.error && !rep.data ? (
        rep.error.status === 409 || rep.error.status === 404 ? (
          <>
          <h1>Class report</h1>
          <Callout tone="warn" title={rep.error.status === 404 ? "That exam does not exist" : "The report is not ready"}>
            {rep.error.message} <Link to="/teacher">Back to your exams</Link>
          </Callout>
          </>
        ) : (
          <ErrorBlock error={rep.error} level={1} onRetry={rep.reload} />
        )
      ) : rep.data ? (
        <View
          data={rep.data}
          linkBase={system.data?.link_base ?? window.location.origin}
          system={system.data}
          refreshing={rep.refreshing}
          updatedAt={rep.updatedAt}
          refreshError={rep.error?.message ?? null}
          reload={rep.reload}
        />
      ) : null}
    </>
  );
}

interface ViewProps {
  data: ReportOut;
  linkBase: string;
  system: Parameters<typeof DataTab>[0]["system"];
  refreshing: boolean;
  updatedAt: number | null;
  refreshError: string | null;
  reload: () => void;
}

function View({ data, linkBase, system, refreshing, updatedAt, refreshError, reload }: ViewProps) {
  const p = useReportParams();
  const { exam, report, scores, questions, build_report } = data;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const s = report.students;
  const link = studentLink(linkBase, exam.code);

  async function toggleOpen() {
    setBusy(true);
    setActionError(null);
    try {
      await api.examAction(exam.code, exam.status === "closed" ? "reopen" : "close");
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const tabLink = (id: string) => {
    const next = new URLSearchParams(p.search);
    next.set("tab", id);
    return `?${next.toString()}`;
  };

  return (
    <>
      <header className="page__head report__head">
        <div className="report__title">
          <h1>{exam.title}</h1>
          <ExamStatusPill status={exam.status} />
        </div>
        <p className="report__meta">
          <span>Code <span className="code">{exam.code}</span></span>
          <span><span className="figure">{exam.joined}</span> of <span className="figure">{exam.max_students}</span> seats used</span>
          <span><span className="figure">{exam.finished}</span> finished</span>
        </p>
        <div className="report__share">
          <div className="linkrow">
            <label className="visually-hidden" htmlFor="student-link">Student link</label>
            <input id="student-link" className="input input--link" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
            <CopyButton text={link} />
          </div>
          <Button icon={exam.status === "closed" ? "unlock" : "lock"} busy={busy} onClick={() => void toggleOpen()}>
            {exam.status === "closed" ? "Reopen" : "Close to new students"}
          </Button>
        </div>
        {actionError ? <Callout tone="error">{actionError}</Callout> : null}
      </header>

      <div className="toolbar" role="group" aria-label="Report filters">
        <span className="toolbar__label" aria-hidden="true">Show</span>
        <Segmented
          name="show"
          legend="Which students to count"
          value={p.include}
          options={[{ value: "all", label: "All" }, { value: "real", label: "Real students" }, { value: "simulated", label: "Test students" }]}
          onChange={(v) => p.set({ show: v === "all" ? null : v })}
        />
        <label className="check">
          <input type="checkbox" checked={p.onlyDone} onChange={(e) => p.set({ done: e.target.checked ? null : "0" })} />
          <span>Only students who finished</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={p.live} onChange={(e) => p.set({ live: e.target.checked ? null : "0" })} />
          <span>Update automatically</span>
        </label>
        <Button small icon="refresh" busy={refreshing} onClick={reload}>Refresh</Button>
        {updatedAt ? <span className="toolbar__stamp figure">Updated {new Date(updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span> : null}
      </div>
      {refreshError ? <Callout tone="warn" title="Could not refresh">{refreshError} Showing the last report we had.</Callout> : null}

      <p className="summary">
        <span className="figure">{s.counted}</span> {s.counted === 1 ? "student" : "students"} shown ({s.real} real, {s.simulated} test)
        {s.in_progress ? `, ${s.in_progress} still taking the exam` : ""}.
      </p>
      {s.simulated ? (
        <Callout tone="info" title="This view includes test students">
          {s.simulated} of the students shown are made up for testing. They are labelled, and the filter above can leave them out.
        </Callout>
      ) : null}

      {s.counted === 0 ? (
        <Empty
          title="No finished students yet"
          action={<Link className="btn btn--quiet" to={tabLink("data")} replace>Add test students</Link>}
        >
          Send the student link above, or add test students to see what the report looks like.
        </Empty>
      ) : (
        <>
          <Reteach cards={report.cards} />
          <MapSection report={report} selected={p.concept} onSelect={(id) => p.set({ concept: id })} />
        </>
      )}

      <section className="tabs" aria-labelledby="details-title">
        <h2 id="details-title" className="visually-hidden">Details</h2>
        <nav className="tabnav" aria-label="Report sections">
          {TABS.map((t) => (
            <Link key={t.id} to={tabLink(t.id)} replace className="tabnav__link" aria-current={p.tab === t.id ? "page" : undefined}>
              {t.label}
            </Link>
          ))}
        </nav>
        {p.tab === "scores" ? <ScoresTab scores={scores} concepts={report.concepts} /> : null}
        {p.tab === "questions" ? <QuestionsTab questions={questions} concepts={report.concepts} selected={p.question} onSelect={(id) => p.set({ q: id })} /> : null}
        {p.tab === "mistakes" ? <MistakesTab report={report} /> : null}
        {p.tab === "data" ? <DataTab exam={exam} system={system} buildReport={build_report} onChanged={reload} /> : null}
      </section>
    </>
  );
}
