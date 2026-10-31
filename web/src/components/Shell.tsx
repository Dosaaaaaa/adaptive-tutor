import { useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Button } from "./Controls";
import { ThemeToggle } from "./ThemeToggle";

export function Brand() {
  return (
    <Link to="/" className="brand" aria-label="Adaptive Tutor, home">
      <svg className="brand__mark" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
        <path className="brand__link" d="M6 17.5L12 7.5M12 7.5l6 10" fill="none" strokeWidth="1.6" strokeLinecap="round" />
        <circle className="brand__node" cx="6" cy="17.5" r="2.6" />
        <circle className="brand__you" cx="12" cy="7.5" r="3" />
        <circle className="brand__node" cx="18" cy="17.5" r="2.6" />
      </svg>
      <span className="brand__name">Adaptive Tutor</span>
    </Link>
  );
}

function SkipLink() {
  return <a className="skip" href="#main">Skip to the content</a>;
}

/** The frame around every student screen: a quiet bar, a narrow column, a note about what is stored. */
export function StudentShell({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="app">
      <SkipLink />
      <header className="topbar">
        <div className="container topbar__in">
          <Brand />
          <div className="topbar__tools"><ThemeToggle /></div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className={wide ? "page container" : "page page--narrow container"}>
        {children}
      </main>
      <footer className="foot">
        <div className="container">
          <p>Only your nickname is saved. No real names are stored.</p>
        </div>
      </footer>
    </div>
  );
}

/** The frame around the teacher's screens: the same bar with the teacher's navigation and sign out. */
export function TeacherShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);

  async function signOut() {
    setLeaving(true);
    try {
      await api.logout();
    } finally {
      navigate("/teacher/login", { replace: true });
    }
  }

  return (
    <div className="app">
      <SkipLink />
      <header className="topbar">
        <div className="container topbar__in">
          <Brand />
          <nav className="topbar__nav" aria-label="Main">
            <NavLink to="/teacher" end className="topbar__link">Exams</NavLink>
          </nav>
          <div className="topbar__tools">
            <ThemeToggle />
            <Button small icon="logout" busy={leaving} onClick={() => void signOut()}>Sign out</Button>
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="page container">
        {children}
      </main>
    </div>
  );
}
