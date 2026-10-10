import { describe, expect, it } from "vitest";

import { formatUptime, sameCommit, shortSha, themeFor } from "./format.js";

describe("themeFor", () => {
  it.each([
    ["production", "production"],
    ["staging", "staging"],
    ["pr-42", "preview"],
    ["preview", "preview"],
    ["local", "local"],
    ["anything", "local"],
  ])("%s maps to %s", (env, theme) => {
    expect(themeFor(env)).toBe(theme);
  });
});

describe("shortSha", () => {
  it("shortens full commit SHAs", () => {
    expect(shortSha("eadd99562dd88a2e31b41c72ba34de2cebc74242")).toBe("eadd995");
  });
  it("leaves unknown and short values alone", () => {
    expect(shortSha(undefined)).toBe("unknown");
    expect(shortSha("unknown")).toBe("unknown");
    expect(shortSha("abc")).toBe("abc");
  });
});

describe("formatUptime", () => {
  it.each([
    [5, "5s"],
    [125, "2m 5s"],
    [3_700, "1h 1m"],
    [90_000, "1d 1h"],
  ])("%d seconds is %s", (seconds, text) => {
    expect(formatUptime(seconds)).toBe(text);
  });
  it("handles missing values", () => {
    expect(formatUptime(undefined)).toBe("n/a");
    expect(formatUptime(-1)).toBe("n/a");
  });
});

describe("sameCommit", () => {
  it("is true only when all known commits match", () => {
    expect(sameCommit(["a1", "a1", "a1"])).toBe(true);
    expect(sameCommit(["a1", "b2", "a1"])).toBe(false);
    expect(sameCommit(["a1", undefined, "unknown", "a1"])).toBe(true);
  });
  it("needs at least two known commits", () => {
    expect(sameCommit(["a1"])).toBe(false);
    expect(sameCommit([undefined, "unknown"])).toBe(false);
  });
});
