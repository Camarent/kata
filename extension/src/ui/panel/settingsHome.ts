import { button, el } from "../dom";
import { TEXT_SETTINGS_HOME } from "../strings";

const [TITLE, CONNECTION, SITES, JOKES, APPEARANCE, ALLOWLIST, IGNORED] = TEXT_SETTINGS_HOME;

/** Settings pages reachable from the settings home. */
export type SettingsPage = "connection" | "sites" | "jokes" | "appearance" | "allowlist" | "ignored";

/** Opens one settings page; the caller swaps the screen. */
export interface SettingsHomeHandlers {
  onOpen: (page: SettingsPage) => void;
}

/** Settings home: one row per page, in the order of the settings strings. */
export function renderSettingsHome(handlers: SettingsHomeHandlers): HTMLElement {
  const screen = el("section", undefined, "settings-home");
  screen.append(el("h2", TITLE));
  const list = el("ul");
  const rows: [SettingsPage, string][] = [
    ["connection", CONNECTION],
    ["sites", SITES],
    ["jokes", JOKES],
    ["appearance", APPEARANCE],
    ["allowlist", ALLOWLIST],
    ["ignored", IGNORED],
  ];
  for (const [page, label] of rows) {
    const item = el("li", undefined, "settings-row");
    item.append(button(label, () => handlers.onOpen(page), `open-${page}`));
    list.append(item);
  }
  screen.append(list);
  return screen;
}
