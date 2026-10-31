import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, messageFrom, UNREACHABLE } from "./api";

function reply(status: number, body: unknown) {
  return new Response(body === undefined ? "" : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("messageFrom", () => {
  it("uses the server's own sentence", () => {
    expect(messageFrom({ detail: "This exam is full." }, 409)).toBe("This exam is full.");
  });

  it("reads the first message of a list", () => {
    expect(messageFrom({ detail: [{ msg: "Field required" }] }, 422)).toBe("Field required");
  });

  it("falls back to plain words that fit the status", () => {
    expect(messageFrom(null, 500)).toMatch(/server/i);
    expect(messageFrom(null, 404)).toMatch(/could not find/i);
    expect(messageFrom({}, 413)).toMatch(/too large/i);
    expect(messageFrom({ detail: "  " }, 400)).toContain("400");
  });
});

describe("api", () => {
  it("sends JSON and returns the parsed answer", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { token: "t1" }));
    vi.stubGlobal("fetch", fetchMock);
    const out = await api.join("K7M2QX", "Sam");
    expect(out).toEqual({ token: "t1" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/exams/K7M2QX/join");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ nickname: "Sam" }));
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("does not set a content type for a file upload, so the browser can add the boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(201, { code: "AAAAAA" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.upload(new FormData());
    expect(fetchMock.mock.calls[0]![1].headers["Content-Type"]).toBeUndefined();
  });

  it("turns an error response into an ApiError with the server's message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(409, { detail: "This exam is full. Please ask your teacher." })));
    await expect(api.join("K7M2QX", "Sam")).rejects.toMatchObject({ status: 409, message: "This exam is full. Please ask your teacher." });
  });

  it("reports an unreachable server in plain words", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.exams().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 0, message: UNREACHABLE });
  });

  it("lets an aborted request through untouched", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    await expect(api.exams()).rejects.toMatchObject({ name: "AbortError" });
  });

  it("tells the app when the teacher's session has ended", async () => {
    const events: string[] = [];
    vi.stubGlobal("window", { dispatchEvent: (e: Event) => events.push(e.type) });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(401, { detail: "Please sign in." })));
    await expect(api.exams()).rejects.toMatchObject({ status: 401 });
    expect(events).toEqual(["tutor:unauthorized"]);
  });

  it("encodes the exam code in the address", () => {
    expect(api.csvUrl("A B")).toBe("/api/exams/A%20B/export.csv");
  });
});
