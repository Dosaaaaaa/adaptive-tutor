// The shapes the API sends. They mirror api/presenters.py and the brain's report functions.

export type MasteryState = "understood" | "shaky" | "missing";
export type ClassStatus = "green" | "orange" | "red";
export type ExamStatus = "building" | "ready" | "closed" | "failed";
export type Include = "all" | "real" | "simulated";

// ---- student ----

export interface PublicExam {
  code: string;
  title: string;
  status: ExamStatus;
  can_join: boolean;
  message: string | null;
}

export interface PlayOption {
  label: string;
  key: string;
  text: string;
}

export interface PlayQuestion {
  id: string;
  stem: string;
  round: number;
  index: number;
  total: number;
  options: PlayOption[];
}

export interface PlayState {
  exam: { code: string; title: string };
  nickname: string;
  round: number;
  index: number;
  total: number;
  phase: "question" | "judging" | "done";
  question: PlayQuestion | null;
}

export interface JoinOut {
  token: string;
  state: PlayState;
}

export interface AnswerBody {
  question_id: string;
  choice: string;
  reason: string;
  is_guess: boolean;
  seconds: number;
}

export interface ConceptResult {
  id: string;
  name: string;
  page: number;
  p: number;
  state: MasteryState;
  answers: number;
}

export interface ReviewItem {
  concept: string;
  page: number;
  question: string;
  your_answer: string;
  correct_answer: string;
  was_right_choice: boolean;
  your_reason: string;
  misconception: string | null;
  explanation: string;
}

export interface Score {
  credited: number;
  asked: number;
  percent: number | null;
  follow_ups: number;
}

export interface ResultsOut {
  nickname: string;
  exam: { code: string; title: string };
  score: Score;
  concepts: ConceptResult[];
  review: ReviewItem[];
}

// ---- teacher ----

export interface Exam {
  code: string;
  title: string;
  bank_name: string | null;
  pdf_name: string | null;
  max_students: number;
  status: ExamStatus;
  max_concepts: number | null;
  error: string | null;
  created_at: string;
  closed_at: string | null;
  joined: number;
  simulated: number;
  finished: number;
  progress?: number;
  message?: string;
}

export interface UploadedExam extends Exam {
  reused: boolean;
}

export interface BankInfo {
  name: string;
  pdf: string | null;
  concepts: number;
  questions: number;
  ai_checked: boolean;
  label: string;
}

export interface SystemInfo {
  mode: "all" | "teacher" | "student";
  link_base: string;
  keys: Record<string, boolean>;
  can_build: boolean;
  ai_problem: string | null;
  banks: BankInfo[];
  counts: Record<string, number>;
  max_upload_mb: number;
  max_pages: number;
  default_concepts: number;
  student_port_hint: number;
}

export interface Me {
  authenticated: boolean;
  password_set: boolean;
  mode: string;
}

export interface Health {
  ok: boolean;
  mode: "all" | "teacher" | "student";
}

export interface TopMistake {
  id: string;
  statement: string;
  students: number;
  quotes: string[];
}

export interface ReportConcept {
  id: string;
  name: string;
  page: number;
  parents: string[];
  n: number;
  understood: number;
  shaky: number;
  missing: number;
  not_understood: number;
  share_understood: number;
  status: ClassStatus;
  status_label: string;
  root_count: number;
  root_share: number;
  start_here: boolean;
  top_mistake: TopMistake | null;
  holds_back: string[];
  headline: string;
}

export interface Mistake {
  id: string;
  concept_id: string;
  concept: string;
  statement: string;
  students: number;
  quotes: string[];
}

export interface ClassReport {
  bank: string;
  students: { counted: number; finished: number; in_progress: number; real: number; simulated: number };
  concepts: ReportConcept[];
  cards: ReportConcept[];
  graph: {
    nodes: { id: string; name: string; status: ClassStatus; understood: number; n: number }[];
    edges: [string, string][];
  };
  mistakes: Mistake[];
  other_texts: { concept_id: string; text: string }[];
}

export interface ScoreRow {
  nickname: string;
  simulated: boolean;
  finished: boolean;
  credited: number;
  asked: number;
  percent: number | null;
  states: Record<string, MasteryState>;
}

export interface Scores {
  students: ScoreRow[];
  average: number | null;
  best: number | null;
  lowest: number | null;
}

export interface QuestionOption {
  key: string;
  text: string;
  tag: string;
  picked: number;
  label: string;
}

export interface QuestionStat {
  question_id: string;
  concept_id: string;
  kind: string;
  round: number;
  stem: string;
  n: number;
  k: number;
  p: number;
  label: "No data" | "Easy" | "Medium" | "Hard";
  flags: string[];
  options: QuestionOption[];
}

export interface ReportOut {
  exam: Exam;
  report: ClassReport;
  scores: Scores;
  questions: QuestionStat[];
  build_report: string | null;
}
