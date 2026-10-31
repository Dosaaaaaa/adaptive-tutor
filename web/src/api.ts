// One place that talks to the server. Every failure becomes an ApiError with a message a person can read.
import type {
  AnswerBody, Exam, Health, Include, JoinOut, Me, PlayState, PublicExam, ReportOut, ResultsOut, SystemInfo, UploadedExam,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const UNREACHABLE = "We could not reach the server. Check your connection and try again.";
export const UNAUTHORIZED_EVENT = "tutor:unauthorized";

/** The sentence to show for a failed response: the server's own message when it sent one. */
export function messageFrom(payload: unknown, status: number): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
      return String((detail[0] as { msg: unknown }).msg);
    }
  }
  if (status >= 500) return "Something went wrong on the server. Please try again in a moment.";
  if (status === 404) return "We could not find that.";
  if (status === 413) return "That file is too large.";
  return `The request did not work (error ${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { credentials: "same-origin", ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, UNREACHABLE);
  }
  const text = await res.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new ApiError(res.status, messageFrom(payload, res.status));
  }
  return payload as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const enc = encodeURIComponent;

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }),

  // student
  publicExam: (code: string, signal?: AbortSignal) => request<PublicExam>(`/exams/${enc(code)}/public`, { signal }),
  join: (code: string, nickname: string) => request<JoinOut>(`/exams/${enc(code)}/join`, json({ nickname })),
  play: (token: string, signal?: AbortSignal) => request<PlayState>(`/play/${enc(token)}`, { signal }),
  answer: (token: string, body: AnswerBody) => request<PlayState>(`/play/${enc(token)}/answer`, json(body)),
  finish: (token: string) => request<PlayState>(`/play/${enc(token)}/finish`, { method: "POST" }),
  results: (token: string, signal?: AbortSignal) => request<ResultsOut>(`/play/${enc(token)}/results`, { signal }),

  // teacher
  me: (signal?: AbortSignal) => request<Me>("/auth/me", { signal }),
  login: (password: string) => request<{ authenticated: boolean }>("/auth/login", json({ password })),
  logout: () => request<{ authenticated: boolean }>("/auth/logout", { method: "POST" }),
  system: (signal?: AbortSignal) => request<SystemInfo>("/system", { signal }),
  exams: (signal?: AbortSignal) => request<Exam[]>("/exams", { signal }),
  exam: (code: string, signal?: AbortSignal) => request<Exam>(`/exams/${enc(code)}`, { signal }),
  createFromBank: (title: string, seats: number, bank: string) => request<Exam>("/exams", json({ title, seats, bank })),
  upload: (form: FormData) => request<UploadedExam>("/exams/upload", { method: "POST", body: form }),
  examAction: (code: string, action: "close" | "reopen" | "stop" | "retry") =>
    request<Exam>(`/exams/${enc(code)}/${action}`, { method: "POST" }),
  deleteExam: (code: string) => request<{ deleted: string; students_removed: number }>(`/exams/${enc(code)}`, { method: "DELETE" }),
  report: (code: string, include: Include, onlyDone: boolean, signal?: AbortSignal) =>
    request<ReportOut>(`/exams/${enc(code)}/report?include=${include}&only_done=${onlyDone}`, { signal }),
  simulate: (code: string, count: number, seed: number) => request<{ added: number }>(`/exams/${enc(code)}/simulate`, json({ count, seed })),
  removeSimulated: (code: string) => request<{ removed: number }>(`/exams/${enc(code)}/simulated`, { method: "DELETE" }),
  csvUrl: (code: string) => `/api/exams/${enc(code)}/export.csv`,
};
