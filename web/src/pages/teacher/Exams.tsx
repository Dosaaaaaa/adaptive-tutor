import { useState } from "react";
import { api } from "../../api";
import { Callout, Empty, ErrorBlock, Loading } from "../../components/States";
import { useResource, useTitle } from "../../hooks";
import type { Exam } from "../../types";
import { ExamRow } from "./ExamRow";
import { NewExam } from "./NewExam";

type Notice = { tone: "ok" | "info"; title: string; text: string };

/** The teacher's home: make an exam on the left, see every exam and its link on the right. */
export default function Exams() {
  useTitle("Exams");
  const system = useResource((signal) => api.system(signal), []);
  const exams = useResource(
    (signal) => api.exams(signal),
    [],
    (list) => (list?.some((e) => e.status === "building") ? 3000 : null),
  );
  const [notice, setNotice] = useState<Notice | null>(null);
  const linkBase = system.data?.link_base ?? window.location.origin;

  function created(exam: Exam, reused: boolean) {
    setNotice(
      exam.status === "building"
        ? { tone: "info", title: `“${exam.title}” is being prepared`, text: "The AI is reading your PDF and writing the questions. This takes several minutes. You can leave this page, and the link appears here when it is ready." }
        : { tone: "ok", title: `“${exam.title}” is ready`, text: reused ? "This quiz was built before, so no waiting was needed. Copy the student link below." : "Copy the student link below and send it to your class." },
    );
    exams.reload();
  }

  return (
    <>
      <header className="page__head">
        <h1>Your exams</h1>
        <p className="lead">Make an exam from a PDF, send the link, then read the class report.</p>
      </header>

      <div className="workspace">
        <section className="workspace__new" aria-labelledby="new-title">
          <h2 id="new-title">New exam</h2>
          {system.loading ? (
            <Loading label="Loading" rows={4} />
          ) : system.error ? (
            <ErrorBlock error={system.error} onRetry={system.reload} />
          ) : system.data ? (
            <NewExam system={system.data} onCreated={created} />
          ) : null}
        </section>

        <section className="workspace__list" aria-labelledby="list-title">
          <h2 id="list-title">Exams</h2>
          {notice ? <Callout tone={notice.tone} title={notice.title}>{notice.text}</Callout> : null}
          {exams.loading ? (
            <Loading label="Loading your exams" rows={4} />
          ) : exams.error && !exams.data ? (
            <ErrorBlock error={exams.error} onRetry={exams.reload} />
          ) : exams.data && exams.data.length === 0 ? (
            <Empty title="No exams yet">Upload a PDF on the left. The first exam appears here with its student link.</Empty>
          ) : (
            <div className="exams">
              {exams.error ? <Callout tone="warn" title="Could not refresh">{exams.error.message} Showing what we had.</Callout> : null}
              {exams.data?.map((e) => <ExamRow key={e.code} exam={e} linkBase={linkBase} onChanged={exams.reload} />)}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
