import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../api";
import { Button, Field } from "../../components/Controls";
import { StudentShell } from "../../components/Shell";
import { Callout, Loading } from "../../components/States";
import { safeNext } from "../../format";
import { useResource, useTitle } from "../../hooks";

export default function Login() {
  useTitle("Teacher sign in");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const me = useResource((signal) => api.me(signal), []);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const signedIn = me.data?.authenticated;
  useEffect(() => {
    if (signedIn) navigate(next, { replace: true });
  }, [signedIn, next, navigate]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password.trim()) {
      setError("Type the teacher password.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.login(password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  const unavailable = me.error?.status === 404;
  return (
    <StudentShell>
      <section className="signin" aria-labelledby="signin-title">
        <h1 id="signin-title">Teacher sign in</h1>
        {me.loading ? (
          <Loading label="Checking your session" rows={2} />
        ) : unavailable ? (
          <>
            <Callout tone="warn" title="Not available here">
              The teacher area is switched off on this address. Students can still use the exam link their teacher shared.
            </Callout>
            <p className="after"><Link to="/">Back to the start</Link></p>
          </>
        ) : (
          <>
            <p className="lead">Only the teacher can see the class report.</p>
            {me.data && !me.data.password_set ? (
              <Callout tone="warn" title="No password is set yet">
                Add TEACHER_PASSWORD to the .env file and restart the server, then sign in here.
              </Callout>
            ) : null}
            <form className="signin__form" onSubmit={submit} noValidate>
              <Field label="Password" error={error}>
                {(control) => (
                  <input
                    {...control}
                    className="input"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                )}
              </Field>
              <Button type="submit" variant="primary" busy={busy} icon="lock">{busy ? "Signing in…" : "Sign in"}</Button>
            </form>
            <p className="after"><Link to="/">I am a student</Link></p>
          </>
        )}
      </section>
    </StudentShell>
  );
}
