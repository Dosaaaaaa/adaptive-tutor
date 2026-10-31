import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { TeacherShell, StudentShell } from "../../components/Shell";
import { Callout, ErrorBlock, Loading } from "../../components/States";
import { useOnUnauthorized, useResource } from "../../hooks";

/** Everything under /teacher except the sign-in page. Without a valid session, the person is sent to sign in. */
export default function TeacherArea() {
  const navigate = useNavigate();
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;
  const me = useResource((signal) => api.me(signal), []);

  useOnUnauthorized(() => navigate(`/teacher/login?next=${encodeURIComponent(here)}`, { replace: true }));

  if (me.loading) {
    return <StudentShell wide><Loading label="Checking your session" rows={2} /></StudentShell>;
  }
  if (me.error?.status === 404) {
    return (
      <StudentShell>
        <h1>Teacher area</h1>
        <Callout tone="warn" title="Not available here">The teacher area is switched off on this address.</Callout>
        <p className="after"><Link to="/">Back to the start</Link></p>
      </StudentShell>
    );
  }
  if (me.error) {
    return <StudentShell wide><ErrorBlock error={me.error} level={1} onRetry={me.reload} /></StudentShell>;
  }
  if (!me.data?.authenticated) {
    return <Navigate to={`/teacher/login?next=${encodeURIComponent(here)}`} replace />;
  }
  return (
    <TeacherShell>
      <Outlet />
    </TeacherShell>
  );
}
