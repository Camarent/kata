/**
 * Composes the browser-specific MV3 manifest from `manifest.base.json`.
 *
 * Pure function: no file system access. The caller reads the base file and writes the result.
 *
 * Firefox: `browser_specific_settings.gecko.id` is `kata@kata.invalid` (a reserved domain, so it
 * never collides with a real add-on); `strict_min_version` is `128.0` (the chosen minimum, see
 * docs/decisions.md). Change both only together with the Firefox add-on listing.
 *
 * `manifest.version` is stamped by the caller (see `build.mjs`), never read from `base`.
 */

/** Gecko add-on id for the Firefox build. */
const GECKO_ID = "kata@kata.invalid";

/** Lowest Firefox version the extension runs on. */
const GECKO_MIN_VERSION = "128.0";

/** Name of the side panel page, relative to the extension root. */
const PANEL_PAGE = "sidepanel.html";

/** Name of the background script, relative to the extension root. */
const BACKGROUND_SCRIPT = "background.js";

/**
 * Returns the manifest for one browser.
 * @param {object} base Parsed `manifest.base.json`; not modified.
 * @param {"chrome" | "firefox"} browser Target browser.
 * @param {string} version Extension version written to `manifest.version`.
 * @returns {object} A new manifest object.
 */
export function composeManifest(base, browser, version) {
  const manifest = structuredClone(base);
  manifest.version = version;
  if (browser === "chrome") {
    manifest.permissions = [...base.permissions, "sidePanel"];
    manifest.side_panel = { default_path: PANEL_PAGE };
    manifest.background = { service_worker: BACKGROUND_SCRIPT, type: "module" };
    return manifest;
  }
  if (browser === "firefox") {
    manifest.sidebar_action = { default_panel: PANEL_PAGE };
    manifest.background = { scripts: [BACKGROUND_SCRIPT], type: "module" };
    manifest.browser_specific_settings = {
      gecko: { id: GECKO_ID, strict_min_version: GECKO_MIN_VERSION },
    };
    return manifest;
  }
  throw new Error(`unknown browser: ${browser}`);
}
