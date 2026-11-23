import { describe, expect, it } from "vitest";
import { matchesStop } from "../src/stopPatterns";

describe("matchesStop", () => {
  it("returns true when a pattern matches the text", () => {
    expect(matchesStop("please stop now", ["^please", "nothing"])).toBe(true);
  });

  it("returns false when no pattern matches the text", () => {
    expect(matchesStop("keep going", ["stop", "halt"])).toBe(false);
  });

  it("skips an invalid regular expression and still checks the others", () => {
    expect(matchesStop("halt here", ["([unclosed", "halt"])).toBe(true);
    expect(matchesStop("keep going", ["([unclosed"])).toBe(false);
  });

  it("returns false for an empty pattern list", () => {
    expect(matchesStop("anything", [])).toBe(false);
  });
});
