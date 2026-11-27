import { describe, expect, it } from "vitest";
import { validateServerUrl } from "../src/serverUrl";

describe("validateServerUrl", () => {
  it("accepts http and https and reports origin and pattern", () => {
    expect(validateServerUrl("https://kata.example.com")).toEqual({
      ok: true,
      baseUrl: "https://kata.example.com",
      origin: "https://kata.example.com",
      pattern: "https://kata.example.com/*",
    });
    expect(validateServerUrl("http://localhost:8080")).toMatchObject({
      ok: true,
      baseUrl: "http://localhost:8080",
      origin: "http://localhost:8080",
    });
  });

  it("trims whitespace and trailing slashes", () => {
    expect(validateServerUrl("  https://kata.example.com//  ")).toMatchObject({
      ok: true,
      baseUrl: "https://kata.example.com",
    });
  });

  it("keeps an optional base path", () => {
    expect(validateServerUrl("https://host.example/kata/api/")).toEqual({
      ok: true,
      baseUrl: "https://host.example/kata/api",
      origin: "https://host.example",
      pattern: "https://host.example/*",
    });
  });

  it.each([
    "javascript:alert(1)",
    "data:text/plain,hi",
    "ftp://files.example.com",
  ])("rejects non-http scheme %s", (input) => {
    const result = validateServerUrl(input);
    expect(result.ok).toBe(false);
  });

  it("rejects embedded credentials", () => {
    expect(validateServerUrl("https://user:pw@kata.example.com")).toMatchObject({ ok: false });
    expect(validateServerUrl("https://user@kata.example.com")).toMatchObject({ ok: false });
  });

  it("rejects a query or fragment", () => {
    expect(validateServerUrl("https://kata.example.com/?x=1")).toMatchObject({ ok: false });
    expect(validateServerUrl("https://kata.example.com/#top")).toMatchObject({ ok: false });
  });

  it("rejects empty and malformed input with a reason", () => {
    expect(validateServerUrl("   ")).toEqual({ ok: false, reason: "server URL is empty" });
    expect(validateServerUrl("not a url")).toEqual({ ok: false, reason: "server URL is not a valid URL" });
  });
});
