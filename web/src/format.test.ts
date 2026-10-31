import { describe, expect, it } from "vitest";
import { difficultyOrder, flagText, normalizeCode, plural, ratioPercent, safeNext, shortDate, studentLink, wordCount, wrapLabel } from "./format";

describe("wordCount", () => {
  it("counts words the way the server does", () => {
    expect(wordCount("")).toBe(0);
    expect(wordCount("  ")).toBe(0);
    expect(wordCount("Because current needs a closed loop")).toBe(6);
    expect(wordCount("it's well-known")).toBe(4);
    expect(wordCount("voltage? yes, voltage!")).toBe(3);
  });

  it("counts letters outside a-z", () => {
    expect(wordCount("más corriente")).toBe(2);
  });
});

describe("normalizeCode", () => {
  it("keeps capitals and digits, caps the length", () => {
    expect(normalizeCode("ab-c 12")).toBe("ABC12");
    expect(normalizeCode("abcdefghijklmnopq")).toHaveLength(12);
  });
});

describe("plural", () => {
  it("uses the singular for exactly one", () => {
    expect(plural(1, "student")).toBe("1 student");
    expect(plural(0, "student")).toBe("0 students");
    expect(plural(2, "city", "cities")).toBe("2 cities");
  });
});

describe("small helpers", () => {
  it("rounds shares to whole percents", () => {
    expect(ratioPercent(0.6667)).toBe(67);
  });

  it("builds a student link without a double slash", () => {
    expect(studentLink("http://192.168.1.4:8080/", "K7M2QX")).toBe("http://192.168.1.4:8080/e/K7M2QX");
  });

  it("turns flags into plain words", () => {
    expect(flagText("check_question")).toBe("Check this question");
    expect(flagText("something_new")).toBe("something new");
  });

  it("orders difficulty hardest first", () => {
    expect(difficultyOrder("Hard")).toBeLessThan(difficultyOrder("Easy"));
    expect(difficultyOrder("No data")).toBe(3);
  });

  it("returns nothing for a missing or broken date", () => {
    expect(shortDate(null)).toBe("");
    expect(shortDate("not a date")).toBe("");
    expect(shortDate("2026-10-31T18:21:00+00:00")).not.toBe("");
  });
});

describe("wrapLabel", () => {
  it("keeps short names on one line", () => {
    expect(wrapLabel("Voltage", 20, 2)).toEqual(["Voltage"]);
  });

  it("wraps at word boundaries", () => {
    expect(wrapLabel("Series and parallel circuits", 14, 3)).toEqual(["Series and", "parallel", "circuits"]);
  });

  it("cuts with an ellipsis when it would need too many lines", () => {
    const lines = wrapLabel("Resistance and the relationship between current and voltage", 14, 2);
    expect(lines).toHaveLength(2);
    expect(lines[1]!.endsWith("…")).toBe(true);
  });

  it("does not split a single very long word", () => {
    expect(wrapLabel("Electromagnetism", 8, 2)).toEqual(["Electromagnetism"]);
  });
});

describe("safeNext", () => {
  it("keeps pages inside the teacher area", () => {
    expect(safeNext("/teacher/exams/K7M2QX?tab=scores")).toBe("/teacher/exams/K7M2QX?tab=scores");
  });

  it("refuses anything that could leave the app", () => {
    expect(safeNext("https://example.com")).toBe("/teacher");
    expect(safeNext("//example.com")).toBe("/teacher");
    expect(safeNext("/teacher\\evil")).toBe("/teacher");
    expect(safeNext("/play/abc")).toBe("/teacher");
    expect(safeNext(null)).toBe("/teacher");
  });
});
