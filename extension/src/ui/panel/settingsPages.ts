import { button, el } from "../dom";
import {
  TEXT_SETTINGS_ALLOWLIST,
  TEXT_SETTINGS_APPEARANCE,
  TEXT_SETTINGS_CONNECTION,
  TEXT_SETTINGS_JOKES,
  TEXT_SETTINGS_SITES,
  TEXT_SIGNOUT_CONFIRM,
} from "../strings";

const [C_TITLE, SERVER_URL, DEVICE_LABEL, CONNECTED, SERVER_DOWN, SIGN_OUT, C_BACK] = TEXT_SETTINGS_CONNECTION;
const [SO_TITLE, SO_UNSYNCED, SO_CONFIRM, SO_CANCEL, SO_FAILED] = TEXT_SIGNOUT_CONFIRM;
const [S_TITLE, S_NOTE, S_REMOVE, S_BACK, S_EMPTY] = TEXT_SETTINGS_SITES;
const [J_TITLE, J_SHOW, J_ONCE, J_HOURS, J_SOURCE, J_NOTE, J_BACK] = TEXT_SETTINGS_JOKES;
const [A_TITLE, A_THEME, A_LIGHT, A_DARK, A_SYSTEM, A_BACK] = TEXT_SETTINGS_APPEARANCE;
const [L_TITLE, TIER1, TIER2, GENERAL_NOTE, ADD_DOMAIN, START_NOTE, MAKE_TIER1, L_REMOVE, FREE_NOTE, L_BACK] =
  TEXT_SETTINGS_ALLOWLIST;

/** Back button, shown only when the caller gives a handler. */
function backButton(label: string, onBack: (() => void) | undefined): HTMLElement[] {
  return onBack === undefined ? [] : [button(label, onBack, "back")];
}

/** Props of the connection page: the server, the device label and whether the server answers. */
export interface SettingsConnectionProps {
  baseUrl: string;
  deviceLabel: string;
  serverUp: boolean;
}

/** Connection settings: server URL, device label, Connected or Server down, Sign out and Back. */
export function renderSettingsConnection(
  props: SettingsConnectionProps,
  handlers: { onSignOut: () => void; onBack?: () => void },
): HTMLElement {
  const screen = el("section", undefined, "settings-connection");
  screen.append(
    el("h2", C_TITLE),
    el("p", `${SERVER_URL}: ${props.baseUrl}`, "origin"),
    el("p", `${DEVICE_LABEL}: ${props.deviceLabel}`, "device"),
    el("p", props.serverUp ? CONNECTED : SERVER_DOWN, "conn-state"),
    button(SIGN_OUT, () => handlers.onSignOut(), "sign-out"),
    ...backButton(C_BACK, handlers.onBack),
  );
  return screen;
}

/** Props of the sign-out confirm: marks not yet synced, and whether the last sign-out failed. */
export interface SignOutConfirmProps {
  unsynced: number;
  failed: boolean;
}

/**
 * Sign-out confirm. The unsynced note appears only when marks wait; its count follows the number of
 * unsynced marks. "Could not sign out." appears after a failed attempt. A rejected `onConfirm` is caught
 * here so no unhandled rejection is raised; the caller shows the failure by re-rendering with `failed: true`.
 */
export function renderSignOutConfirm(
  props: SignOutConfirmProps,
  handlers: { onConfirm: () => void | Promise<void>; onCancel: () => void },
): HTMLElement {
  const screen = el("section", undefined, "signout-confirm");
  screen.append(el("h2", SO_TITLE));
  if (props.unsynced > 0) {
    // The string names "3 marks are not synced."; the count is live (no singular copy is approved).
    const note = SO_UNSYNCED.replace(/^\d+/, String(props.unsynced));
    screen.append(el("p", note, "note"));
  }
  if (props.failed) {
    screen.append(el("p", SO_FAILED, "error"));
  }
  const confirm = async () => {
    try {
      await handlers.onConfirm();
    } catch {
      // The caller owns the failure message (failed: true on its next render).
    }
  };
  screen.append(
    button(SO_CONFIRM, () => void confirm(), "confirm-sign-out"),
    button(SO_CANCEL, () => handlers.onCancel(), "cancel-sign-out"),
  );
  return screen;
}

/** Auto-scan sites: each site with Remove; "No sites yet." when the list is empty. */
export function renderSettingsSites(
  props: { sites: string[] },
  handlers: { onRemove: (site: string) => void; onBack?: () => void },
): HTMLElement {
  const screen = el("section", undefined, "settings-sites");
  screen.append(el("h2", S_TITLE), el("p", S_NOTE, "note"));
  if (props.sites.length === 0) {
    screen.append(el("p", S_EMPTY, "empty"));
  } else {
    const list = el("ul");
    for (const site of props.sites) {
      const item = el("li", undefined, "site-row");
      item.append(el("span", site, "site"), button(S_REMOVE, () => handlers.onRemove(site), "remove-site"));
      list.append(item);
    }
    screen.append(list);
  }
  screen.append(...backButton(S_BACK, handlers.onBack));
  return screen;
}

/** Jokes settings: the Show jokes switch, the frequency line and the source. */
export function renderSettingsJokes(
  props: { enabled: boolean; source: string },
  handlers: { onToggle: (enabled: boolean) => void; onBack?: () => void },
): HTMLElement {
  const screen = el("section", undefined, "settings-jokes");
  const label = el("label", undefined, "show-jokes");
  const box = el("input");
  box.type = "checkbox";
  box.checked = props.enabled;
  box.addEventListener("change", () => handlers.onToggle(box.checked));
  label.append(box, el("span", J_SHOW));
  screen.append(
    el("h2", J_TITLE),
    label,
    el("p", `${J_ONCE} ${J_HOURS}`, "frequency"),
    el("p", `${J_SOURCE}: ${props.source}`, "source"),
    el("p", J_NOTE, "note"),
    ...backButton(J_BACK, handlers.onBack),
  );
  return screen;
}

/** Theme choices of the appearance page. */
export type ThemeChoice = "light" | "dark" | "system";

/** Appearance settings: Light, Dark and System; the chosen theme shows as pressed. */
export function renderSettingsAppearance(
  props: { theme: ThemeChoice },
  handlers: { onTheme: (theme: ThemeChoice) => void; onBack?: () => void },
): HTMLElement {
  const screen = el("section", undefined, "settings-appearance");
  const choices: [ThemeChoice, string][] = [
    ["light", A_LIGHT],
    ["dark", A_DARK],
    ["system", A_SYSTEM],
  ];
  screen.append(el("h2", A_TITLE), el("p", A_THEME, "theme-label"));
  for (const [theme, text] of choices) {
    const choice = button(text, () => handlers.onTheme(theme), `theme-${theme}`);
    choice.setAttribute("aria-pressed", String(props.theme === theme));
    screen.append(choice);
  }
  screen.append(...backButton(A_BACK, handlers.onBack));
  return screen;
}

/** Props of the allowed sources: the Tier 1 and Tier 2 domains. */
export interface AllowlistProps {
  tier1: string[];
  tier2: string[];
}

/**
 * Allowed sources: Tier 1 with its general note, Tier 2, an add-domain field (new domains start in
 * Tier 2), Make Tier 1 and Remove per domain, and the free-to-read note.
 */
export function renderSettingsAllowlist(
  props: AllowlistProps,
  handlers: {
    onAdd: (domain: string) => void;
    onPromote: (domain: string) => void;
    onRemove: (domain: string) => void;
    onBack?: () => void;
  },
): HTMLElement {
  const screen = el("section", undefined, "settings-allowlist");
  screen.append(el("h2", L_TITLE));
  screen.append(el("h3", TIER1), el("p", GENERAL_NOTE, "note"));
  screen.append(domainList(props.tier1, false, handlers));
  screen.append(el("h3", TIER2), domainList(props.tier2, true, handlers));

  const form = el("form", undefined, "add-domain");
  const input = el("input");
  input.type = "text";
  const add = el("button", ADD_DOMAIN, "add-domain-button");
  add.type = "submit";
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const domain = input.value.trim();
    if (domain === "") return;
    handlers.onAdd(domain);
  });
  form.append(input, add, el("p", START_NOTE, "note"));
  screen.append(form, el("p", FREE_NOTE, "note"));
  screen.append(...backButton(L_BACK, handlers.onBack));
  return screen;
}

/** One tier of domains; Tier 2 rows offer Make Tier 1, and every row offers Remove. */
function domainList(
  domains: string[],
  promotable: boolean,
  handlers: { onPromote: (domain: string) => void; onRemove: (domain: string) => void },
): HTMLElement {
  const list = el("ul");
  for (const domain of domains) {
    const item = el("li", undefined, "domain-row");
    item.append(el("span", domain, "domain"));
    if (promotable) {
      item.append(button(MAKE_TIER1, () => handlers.onPromote(domain), "make-tier1"));
    }
    item.append(button(L_REMOVE, () => handlers.onRemove(domain), "remove-domain"));
    list.append(item);
  }
  return list;
}
