import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Script } from "node:vm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

/** `npm --prefix extension test` runs with the extension folder as cwd. */
const EXTENSION_DIR = process.cwd();
/** The build runs tsc and esbuild; allow it a generous window on a cold cache. */
const BUILD_TIMEOUT_MS = 120_000;
const BROWSERS = ["firefox", "chrome"] as const;
/** Files every browser output folder must contain. */
const OUTPUT_FILES = ["manifest.json", "background.js", "content.js", "bridge.js", "sidepanelBoot.js", "sidepanel.html"];

function distPath(browser: string, file: string): string {
  return join(EXTENSION_DIR, "dist", browser, file);
}

function readManifest(browser: string): Record<string, unknown> {
  return JSON.parse(readFileSync(distPath(browser, "manifest.json"), "utf8"));
}

describe("built extension", () => {
  beforeAll(() => {
    execSync("npm run build", { cwd: EXTENSION_DIR, stdio: "pipe" });
  }, BUILD_TIMEOUT_MS);

  it.each(BROWSERS)("dist/%s has every output file", (browser) => {
    for (const file of OUTPUT_FILES) {
      expect(existsSync(distPath(browser, file)), file).toBe(true);
    }
  });

  it.each(BROWSERS)("dist/%s/content.js is a classic script: no top-level import or export", (browser) => {
    const source = readFileSync(distPath(browser, "content.js"), "utf8");
    // A classic script compiles as one; a top-level import or export is a SyntaxError.
    expect(() => new Script(source, { filename: "content.js" })).not.toThrow();
  });

  it.each(BROWSERS)("dist/%s/bridge.js is a classic script that carries the stub source", (browser) => {
    const source = readFileSync(distPath(browser, "bridge.js"), "utf8");
    // The stub text is injected into the page at run time; the bundle must hold it verbatim.
    expect(() => new Script(source, { filename: "bridge.js" })).not.toThrow();
    expect(source).toContain("win.claude");
  });

  it("firefox manifest uses sidebar_action and the gecko id, not side_panel", () => {
    const manifest = readManifest("firefox");
    expect(manifest.sidebar_action).toBeDefined();
    expect(manifest.side_panel).toBeUndefined();
    expect(manifest.browser_specific_settings).toEqual({
      gecko: { id: "kata@kata.local", strict_min_version: "128.0" },
    });
  });

  it("chrome manifest uses side_panel, not sidebar_action", () => {
    const manifest = readManifest("chrome");
    expect(manifest.side_panel).toBeDefined();
    expect(manifest.sidebar_action).toBeUndefined();
  });
});

describe("built extension with KATA_EXTENSION_BASE_URL", () => {
  const CUSTOM_URL = "http://127.0.0.1:9090";

  /** Runs `node build/build.mjs firefox` with the base URL variable set, or unset when undefined. */
  function buildFirefox(baseUrl: string | undefined): void {
    const env: NodeJS.ProcessEnv = { ...process.env };
    delete env.KATA_EXTENSION_BASE_URL;
    if (baseUrl !== undefined) env.KATA_EXTENSION_BASE_URL = baseUrl;
    execSync("node build/build.mjs firefox", { cwd: EXTENSION_DIR, env, stdio: "pipe" });
  }

  beforeAll(() => {
    buildFirefox(CUSTOM_URL);
  }, BUILD_TIMEOUT_MS);

  afterAll(() => {
    // Restore the default build that the other tests in this file read.
    buildFirefox(undefined);
  }, BUILD_TIMEOUT_MS);

  it("manifest host_permissions is exactly the configured origin", () => {
    expect(readManifest("firefox").host_permissions).toEqual(["http://127.0.0.1:9090/*"]);
  });

  it("the bundled background script carries the configured URL", () => {
    const bundle = readFileSync(distPath("firefox", "background.js"), "utf8");
    expect(bundle).toContain(JSON.stringify(CUSTOM_URL));
  });

  it("an unset variable gives the default host permission again", () => {
    buildFirefox(undefined);
    expect(readManifest("firefox").host_permissions).toEqual(["http://127.0.0.1:8080/*"]);
  });
});
