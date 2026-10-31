import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Button, ButtonLink, Field } from "../components/Controls";
import { StudentShell } from "../components/Shell";
import { normalizeCode } from "../format";
import { useResource, useTitle } from "../hooks";

/** The front door: students type a code, teachers sign in. */
export default function Home() {
  useTitle("Take your exam");
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const health = useResource((signal) => api.health(signal), []);
  const teacherAvailable = health.data?.mode !== "student";

  function go(event: FormEvent) {
    event.preventDefault();
    const clean = normalizeCode(code);
    if (clean.length < 4) {
      setError("Type the code your teacher gave you. It has 6 letters and numbers.");
      return;
    }
    setError(null);
    navigate(`/e/${clean}`);
  }

  return (
    <StudentShell wide>
      <div className="door">
        <section className="door__main" aria-labelledby="door-title">
          <h1 id="door-title">Take your exam</h1>
          <p className="lead">Type the code your teacher gave you, or open the link they sent.</p>
          <form className="door__form" onSubmit={go} noValidate>
            <Field label="Exam code" hint="6 letters and numbers, like K7M2QX." error={error}>
              {(control) => (
                <input
                  {...control}
                  className="input input--code"
                  value={code}
                  onChange={(e) => setCode(normalizeCode(e.target.value))}
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  maxLength={12}
                />
              )}
            </Field>
            <Button type="submit" variant="primary">Continue</Button>
          </form>
        </section>
        {teacherAvailable ? (
          <aside className="door__aside" aria-labelledby="teacher-title">
            <h2 id="teacher-title">Are you the teacher?</h2>
            <p>Turn a PDF into an exam, send one link to the class, and see which concepts to teach again.</p>
            <ButtonLink to="/teacher" icon="lock">Teacher sign in</ButtonLink>
          </aside>
        ) : null}
      </div>
    </StudentShell>
  );
}
