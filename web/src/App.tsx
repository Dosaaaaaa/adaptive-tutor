import { lazy, Suspense, useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { StudentShell } from "./components/Shell";
import { Loading } from "./components/States";
import { useTitle } from "./hooks";
import Home from "./pages/Home";
import Join from "./pages/Join";
import Play from "./pages/Play";
import Results from "./pages/Results";

// The teacher's screens are only needed by teachers, so students never download them.
const Login = lazy(() => import("./pages/teacher/Login"));
const TeacherArea = lazy(() => import("./pages/teacher/TeacherArea"));
const Exams = lazy(() => import("./pages/teacher/Exams"));
const Report = lazy(() => import("./pages/teacher/Report"));

function NotFound() {
  useTitle("Page not found");
  return (
    <StudentShell>
      <section aria-labelledby="nf-title">
        <h1 id="nf-title">That page does not exist</h1>
        <p className="lead">Check the link, or start from the front door.</p>
        <p className="after"><Link to="/">Go to the start</Link></p>
      </section>
    </StudentShell>
  );
}

/** After each move to a new page, send keyboard and screen-reader focus to the top of it, as a full page load would. */
function useFocusOnNavigate() {
  const { pathname } = useLocation();
  useEffect(() => {
    const main = document.getElementById("main");
    main?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [pathname]);
}

export default function App() {
  useFocusOnNavigate();
  return (
    <Suspense fallback={<StudentShell wide><Loading label="Loading" rows={2} /></StudentShell>}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/e/:code" element={<Join />} />
        <Route path="/play/:token" element={<Play />} />
        <Route path="/play/:token/results" element={<Results />} />
        <Route path="/teacher/login" element={<Login />} />
        <Route path="/teacher" element={<TeacherArea />}>
          <Route index element={<Exams />} />
          <Route path="exams/:code" element={<Report />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
