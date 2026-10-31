import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../../api";
import { Button, Field, Segmented } from "../../components/Controls";
import { Callout } from "../../components/States";
import type { Exam, SystemInfo } from "../../types";

type Source = "pdf" | "bank";
type Problems = Partial<Record<"title" | "seats" | "file" | "concepts" | "bank", string>>;

interface Props {
  system: SystemInfo;
  onCreated: (exam: Exam, reused: boolean) => void;
}

const megabytes = (bytes: number) => (bytes / (1024 * 1024)).toFixed(1);

/** The form that turns a PDF (or a ready-made quiz) into an exam with a seat limit. */
export function NewExam({ system, onCreated }: Props) {
  const canBuild = system.can_build;
  const [source, setSource] = useState<Source>(canBuild || system.banks.length === 0 ? "pdf" : "bank");
  const [title, setTitle] = useState("");
  const [seats, setSeats] = useState("30");
  const [concepts, setConcepts] = useState(String(system.default_concepts));
  const [bank, setBank] = useState(system.banks[0]?.name ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [problems, setProblems] = useState<Problems>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  function check(): Problems {
    const found: Problems = {};
    const seatCount = Number(seats);
    if (!title.trim()) found.title = "Give the exam a title your class will recognise.";
    if (!Number.isInteger(seatCount) || seatCount < 1 || seatCount > 1000) found.seats = "Choose a whole number from 1 to 1000.";
    if (source === "pdf") {
      const conceptCount = Number(concepts);
      if (!file) found.file = "Choose the PDF with your notes.";
      else if (!/\.pdf$/i.test(file.name)) found.file = "That file is not a PDF.";
      else if (file.size > system.max_upload_mb * 1024 * 1024) found.file = `That file is ${megabytes(file.size)} MB. The limit is ${system.max_upload_mb} MB.`;
      if (!Number.isInteger(conceptCount) || conceptCount < 2 || conceptCount > 15) found.concepts = "Choose a number from 2 to 15.";
    } else if (!bank) {
      found.bank = "Choose a quiz.";
    }
    return found;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = check();
    setProblems(found);
    setFailure(null);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      if (source === "pdf" && file) {
        const form = new FormData();
        form.set("title", title.trim());
        form.set("seats", seats);
        form.set("max_concepts", concepts);
        form.set("file", file);
        const made = await api.upload(form);
        onCreated(made, made.reused);
      } else {
        onCreated(await api.createFromBank(title.trim(), Number(seats), bank), true);
      }
      setTitle("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const options: { value: Source; label: string }[] = [{ value: "pdf", label: "Upload a PDF" }];
  if (system.banks.length) options.push({ value: "bank", label: "Use a ready quiz" });

  return (
    <form className="newexam" onSubmit={submit} noValidate>
      {options.length > 1 ? <Segmented name="source" legend="Where the questions come from" value={source} options={options} onChange={setSource} /> : null}

      {source === "pdf" && !canBuild ? (
        <Callout tone="warn" title="Building from a PDF is not set up">
          {system.ai_problem ?? "Add a free AI key to the .env file."}{system.banks.length ? " You can still use a ready quiz." : ""}
        </Callout>
      ) : null}

      <Field label="Title" error={problems.title}>
        {(control) => <input {...control} className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} autoComplete="off" />}
      </Field>

      {source === "pdf" ? (
        <>
          <Field label="Your notes as a PDF" hint={`Up to ${system.max_upload_mb} MB and ${system.max_pages} pages. The text must be selectable, not a scan.`} error={problems.file}>
            {(control) => (
              <input
                {...control}
                ref={fileInput}
                className="input input--file"
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                disabled={!canBuild}
              />
            )}
          </Field>
          <details className="more">
            <summary>More options</summary>
            <Field label="Concepts to find" hint="Five suits a 5 to 7 page handout. Use 12 to 15 for a long chapter." error={problems.concepts}>
              {(control) => (
                <input {...control} className="input input--short figure" type="number" min={2} max={15} value={concepts} onChange={(e) => setConcepts(e.target.value)} />
              )}
            </Field>
          </details>
        </>
      ) : (
        <Field label="Quiz" hint={system.banks.find((b) => b.name === bank)?.label} error={problems.bank}>
          {(control) => (
            <select {...control} className="input" value={bank} onChange={(e) => setBank(e.target.value)}>
              {system.banks.map((b) => <option key={b.name} value={b.name}>{b.pdf ?? b.name}</option>)}
            </select>
          )}
        </Field>
      )}

      <Field label="Seats" hint="How many students may use the link." error={problems.seats}>
        {(control) => (
          <input {...control} className="input input--short figure" type="number" min={1} max={1000} value={seats} onChange={(e) => setSeats(e.target.value)} />
        )}
      </Field>

      {failure ? <Callout tone="error" title="The exam was not created">{failure}</Callout> : null}

      <Button type="submit" variant="primary" busy={busy} icon="upload" disabled={source === "pdf" && !canBuild}>
        {busy ? (source === "pdf" ? "Uploading…" : "Creating…") : "Create exam"}
      </Button>
    </form>
  );
}
