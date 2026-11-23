/**
 * Builds the extension for each browser into `dist/<browser>/`.
 *
 * Usage: `node build/build.mjs [chrome|firefox]`. Without an argument both browsers are built.
 * Each selected browser's output folder is removed first, then written: manifest.json (from
 * `composeManifest`), the bundled scripts, and a copy of sidepanel.html.
 */

import { build } from "esbuild";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { composeManifest } from "./manifest.mjs";

const EXTENSION_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const DIST_DIR = join(EXTENSION_DIR, "dist");
const BROWSERS = ["chrome", "firefox"];
const PANEL_PAGE = "sidepanel.html";

/** Scripts bundled for every browser; `out` is relative to `dist/<browser>/`. */
const SCRIPTS = [
  { entry: "src/background.ts", out: "background.js", format: "esm" },
  { entry: "src/content.ts", out: "content.js", format: "iife" },
  { entry: "src/bridge.ts", out: "bridge.js", format: "iife" },
  { entry: "src/sidepanelBoot.ts", out: "sidepanelBoot.js", format: "esm" },
];

/**
 * Returns the browsers named on the command line, or all of them when none is named.
 * @param {string | undefined} requested Optional `argv[2]`.
 * @returns {string[]}
 */
function selectedBrowsers(requested) {
  if (requested === undefined) return BROWSERS;
  if (!BROWSERS.includes(requested)) throw new Error(`unknown browser: ${requested}`);
  return [requested];
}

/**
 * Writes the full output for one browser.
 * @param {string} browser Target browser.
 * @param {object} base Parsed `manifest.base.json`.
 */
async function buildBrowser(browser, base) {
  const outDir = join(DIST_DIR, browser);
  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });
  await writeFile(join(outDir, "manifest.json"), `${JSON.stringify(composeManifest(base, browser), null, 2)}\n`);
  await copyFile(join(EXTENSION_DIR, PANEL_PAGE), join(outDir, PANEL_PAGE));
  for (const script of SCRIPTS) {
    await build({
      entryPoints: [join(EXTENSION_DIR, script.entry)],
      outfile: join(outDir, script.out),
      bundle: true,
      format: script.format,
      platform: "browser",
      target: "es2022",
      logLevel: "warning",
    });
  }
  console.log(`built ${browser}: ${outDir}`);
}

const base = JSON.parse(await readFile(join(EXTENSION_DIR, "manifest.base.json"), "utf8"));
for (const browser of selectedBrowsers(process.argv[2])) {
  await buildBrowser(browser, base);
}
