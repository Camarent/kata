import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { composeManifest } from "../build/manifest.mjs";

/** `npm --prefix extension test` runs with the extension folder as cwd. */
const EXTENSION_DIR = process.cwd();
/** The shared manifest fields; browser-specific keys are added by `composeManifest`. */
const base = JSON.parse(readFileSync(join(EXTENSION_DIR, "manifest.base.json"), "utf-8"));
/** Version passed by the build; `composeManifest` writes it to `manifest.version`. */
const VERSION = "1.2.3";

describe("composeManifest", () => {
  it("base has no broad host match and no <all_urls>", () => {
    expect(JSON.stringify(base)).not.toContain("<all_urls>");
    expect(base.content_scripts[0].matches).toEqual(["http://*/*", "https://*/*"]);
  });

  it("base declares the permissions API, so chrome.permissions exists in both browsers", () => {
    expect(base.permissions).toContain("permissions");
    for (const browser of ["chrome", "firefox"] as const) {
      expect(composeManifest(base, browser, VERSION).permissions).toContain("permissions");
    }
  });

  it("stamps the given version into both browsers and leaves the base version alone", () => {
    for (const browser of ["chrome", "firefox"] as const) {
      expect(composeManifest(base, browser, VERSION).version).toBe(VERSION);
    }
    expect(base.version).toBe("0.0.0");
  });

  it("base static content scripts are content.js only; bridge.js is registered at runtime", () => {
    expect(base.content_scripts).toHaveLength(1);
    expect(base.content_scripts[0].js).toEqual(["content.js"]);
    expect(JSON.stringify(base)).not.toContain("bridge.js");
  });

  it("chrome adds sidePanel permission, side_panel and a module service worker", () => {
    const m = composeManifest(base, "chrome", VERSION);
    expect(m.permissions).toEqual(["storage", "activeTab", "scripting", "permissions", "sidePanel"]);
    expect(m.side_panel).toEqual({ default_path: "sidepanel.html" });
    expect(m.background).toEqual({ service_worker: "background.js", type: "module" });
    expect(m.sidebar_action).toBeUndefined();
    expect(m.browser_specific_settings).toBeUndefined();
  });

  it("firefox adds sidebar_action, background scripts and gecko id without sidePanel", () => {
    const m = composeManifest(base, "firefox", VERSION);
    expect(m.permissions).toEqual(["storage", "activeTab", "scripting", "permissions"]);
    expect(m.permissions).not.toContain("sidePanel");
    expect(m.side_panel).toBeUndefined();
    expect(m.sidebar_action).toEqual({ default_panel: "sidepanel.html" });
    expect(m.background).toEqual({ scripts: ["background.js"], type: "module" });
    expect(m.browser_specific_settings.gecko).toEqual({
      id: "kata@kata.invalid",
      strict_min_version: "128.0",
    });
  });

  it("keeps the shared fields in both browsers", () => {
    for (const browser of ["chrome", "firefox"] as const) {
      const m = composeManifest(base, browser, VERSION);
      expect(m.manifest_version).toBe(3);
      expect(m.optional_host_permissions).toEqual(["http://*/*", "https://*/*"]);
      expect(m.content_scripts).toEqual(base.content_scripts);
    }
  });

  it("has no fixed host_permissions in either browser", () => {
    for (const browser of ["chrome", "firefox"] as const) {
      expect(composeManifest(base, browser, VERSION).host_permissions).toBeUndefined();
    }
  });

  it("does not modify the base manifest", () => {
    const before = JSON.stringify(base);
    composeManifest(base, "chrome", VERSION);
    composeManifest(base, "firefox", VERSION);
    expect(JSON.stringify(base)).toBe(before);
  });

  it("throws on an unknown browser", () => {
    expect(() => composeManifest(base, "safari" as never, VERSION)).toThrow("unknown browser: safari");
  });

});
