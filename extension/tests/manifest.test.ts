import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { composeManifest } from "../build/manifest.mjs";

/** `npm --prefix extension test` runs with the extension folder as cwd. */
const EXTENSION_DIR = process.cwd();
/** The shared manifest fields; browser-specific keys are added by `composeManifest`. */
const base = JSON.parse(readFileSync(join(EXTENSION_DIR, "manifest.base.json"), "utf-8"));

describe("composeManifest", () => {
  it("base has no broad host match and no <all_urls>", () => {
    expect(JSON.stringify(base)).not.toContain("<all_urls>");
    expect(base.content_scripts[0].matches).toEqual(["http://*/*", "https://*/*"]);
  });

  it("base static content scripts are content.js only; bridge.js is registered at runtime", () => {
    expect(base.content_scripts).toHaveLength(1);
    expect(base.content_scripts[0].js).toEqual(["content.js"]);
    expect(JSON.stringify(base)).not.toContain("bridge.js");
  });

  it("chrome adds sidePanel permission, side_panel and a module service worker", () => {
    const m = composeManifest(base, "chrome");
    expect(m.permissions).toEqual(["storage", "activeTab", "scripting", "sidePanel"]);
    expect(m.side_panel).toEqual({ default_path: "sidepanel.html" });
    expect(m.background).toEqual({ service_worker: "background.js", type: "module" });
    expect(m.sidebar_action).toBeUndefined();
    expect(m.browser_specific_settings).toBeUndefined();
  });

  it("firefox adds sidebar_action, background scripts and gecko id without sidePanel", () => {
    const m = composeManifest(base, "firefox");
    expect(m.permissions).toEqual(["storage", "activeTab", "scripting"]);
    expect(m.permissions).not.toContain("sidePanel");
    expect(m.side_panel).toBeUndefined();
    expect(m.sidebar_action).toEqual({ default_panel: "sidepanel.html" });
    expect(m.background).toEqual({ scripts: ["background.js"], type: "module" });
    expect(m.browser_specific_settings.gecko).toEqual({
      id: "kata@kata.local",
      strict_min_version: "128.0",
    });
  });

  it("keeps the shared fields in both browsers", () => {
    for (const browser of ["chrome", "firefox"] as const) {
      const m = composeManifest(base, browser);
      expect(m.manifest_version).toBe(3);
      expect(m.host_permissions).toEqual(["http://127.0.0.1:8080/*"]);
      expect(m.content_scripts).toEqual(base.content_scripts);
    }
  });

  it("does not modify the base manifest", () => {
    const before = JSON.stringify(base);
    composeManifest(base, "chrome");
    composeManifest(base, "firefox");
    expect(JSON.stringify(base)).toBe(before);
  });

  it("throws on an unknown browser", () => {
    expect(() => composeManifest(base, "safari" as never)).toThrow("unknown browser: safari");
  });

  it("with no base URL keeps host_permissions from the base manifest", () => {
    for (const browser of ["chrome", "firefox"] as const) {
      const m = composeManifest(base, browser);
      expect(m.host_permissions).toEqual(base.host_permissions);
      expect(m.content_scripts).toEqual(base.content_scripts);
    }
  });

  it("sets host_permissions to exactly the origin of the configured base URL", () => {
    for (const browser of ["chrome", "firefox"] as const) {
      const m = composeManifest(base, browser, "https://core.example.test:9443/api/v1");
      expect(m.host_permissions).toEqual(["https://core.example.test:9443/*"]);
      expect(m.content_scripts).toEqual(base.content_scripts);
    }
  });

  it("throws on a base URL that does not parse", () => {
    expect(() => composeManifest(base, "chrome", "not a url")).toThrow("invalid base URL: not a url");
  });

  it("throws on a base URL that is not http or https", () => {
    expect(() => composeManifest(base, "firefox", "ftp://127.0.0.1:8080")).toThrow("must be http or https");
  });
});
