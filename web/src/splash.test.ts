import { describe, expect, it } from "vitest";
import themeInit from "../public/theme-init.js?raw";
import { shouldShowSplash } from "./splash";

describe("shouldShowSplash", () => {
  it("shows once per tab", () => {
    expect(shouldShowSplash("", false)).toBe(true);
    expect(shouldShowSplash("", true)).toBe(false);
    expect(shouldShowSplash("?tab=scores", false)).toBe(true);
  });

  it("can be forced on or off from the address", () => {
    expect(shouldShowSplash("?splash=1", true)).toBe(true);
    expect(shouldShowSplash("?splash=0", false)).toBe(false);
    expect(shouldShowSplash("?a=b&splash=1", true)).toBe(true);
  });
});

// public/theme-init.js decides before the first paint, in plain JavaScript. It must agree with shouldShowSplash.
function decideInPage(search: string, seen: boolean, storageWorks = true): { splash: string; flagWritten: boolean } {
  const attributes: Record<string, string> = {};
  let flagWritten = false;
  const storage = {
    getItem: (key: string) => {
      if (!storageWorks) throw new Error("blocked");
      return key === "tutor-splash" && seen ? "1" : null;
    },
    setItem: (key: string) => {
      if (!storageWorks) throw new Error("blocked");
      if (key === "tutor-splash") flagWritten = true;
    },
  };
  const page = {
    document: { documentElement: { setAttribute: (k: string, v: string) => (attributes[k] = v) } },
    location: { search },
    sessionStorage: storage,
    localStorage: { getItem: () => null },
  };
  new Function("document", "location", "sessionStorage", "localStorage", themeInit)(page.document, page.location, page.sessionStorage, page.localStorage);
  return { splash: attributes["data-splash"] ?? "", flagWritten };
}

describe("public/theme-init.js", () => {
  it("makes the same decision as shouldShowSplash", () => {
    for (const search of ["", "?splash=1", "?splash=0", "?x=1&splash=1", "?splash=2"]) {
      for (const seen of [false, true]) {
        expect(decideInPage(search, seen).splash).toBe(shouldShowSplash(search, seen) ? "show" : "skip");
      }
    }
  });

  it("remembers that the screen was shown, so a reload does not wait for it again", () => {
    expect(decideInPage("", false).flagWritten).toBe(true);
    expect(decideInPage("", true).flagWritten).toBe(false);
  });

  it("never delays anything when the tab cannot remember", () => {
    expect(decideInPage("", false, false).splash).toBe("skip");
  });
});
