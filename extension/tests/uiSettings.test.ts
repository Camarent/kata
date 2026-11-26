import { describe, expect, it, vi } from "vitest";
import { ignoredClientHandlers, renderIgnoredList } from "../src/ui/panel/ignoredList";
import { renderSettingsHome } from "../src/ui/panel/settingsHome";
import {
  renderSettingsAllowlist,
  renderSettingsAppearance,
  renderSettingsConnection,
  renderSettingsJokes,
  renderSettingsSites,
  renderSignOutConfirm,
} from "../src/ui/panel/settingsPages";
import {
  TEXT_IGNORED_LIST,
  TEXT_PIN,
  TEXT_SETTINGS_ALLOWLIST,
  TEXT_SETTINGS_APPEARANCE,
  TEXT_SETTINGS_CONNECTION,
  TEXT_SETTINGS_HOME,
  TEXT_SETTINGS_JOKES,
  TEXT_SETTINGS_SITES,
  TEXT_SIGNOUT_CONFIRM,
} from "../src/ui/strings";

/** Button with the given visible text inside root; fails the test when there is none. */
function buttonNamed(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text);
  if (found === undefined) throw new Error(`no button "${text}"`);
  return found;
}

/** Visible text of the whole screen, one entry per element that has text of its own. */
function allText(root: HTMLElement): string {
  return root.textContent ?? "";
}

describe("settings home", () => {
  it("renders every settings row label and opens its page", () => {
    const onOpen = vi.fn();
    const screen = renderSettingsHome({ onOpen });
    for (const text of TEXT_SETTINGS_HOME.slice(1)) {
      expect(allText(screen)).toContain(text);
    }
    buttonNamed(screen, TEXT_SETTINGS_HOME[6]).click();
    expect(onOpen).toHaveBeenCalledWith("ignored");
    buttonNamed(screen, TEXT_SETTINGS_HOME[1]).click();
    expect(onOpen).toHaveBeenLastCalledWith("connection");
  });
});

describe("settings connection", () => {
  it("shows Connected with Sign out and Back", () => {
    const onSignOut = vi.fn();
    const onBack = vi.fn();
    const screen = renderSettingsConnection(
      { baseUrl: "http://localhost:8000", deviceLabel: "laptop", serverUp: true },
      { onSignOut, onBack },
    );
    expect(allText(screen)).toContain(TEXT_SETTINGS_CONNECTION[1]);
    expect(allText(screen)).toContain(TEXT_SETTINGS_CONNECTION[3]);
    expect(allText(screen)).not.toContain(TEXT_SETTINGS_CONNECTION[4]);
    buttonNamed(screen, TEXT_SETTINGS_CONNECTION[5]).click();
    buttonNamed(screen, TEXT_SETTINGS_CONNECTION[6]).click();
    expect(onSignOut).toHaveBeenCalledOnce();
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("shows Server down when the server does not answer", () => {
    const screen = renderSettingsConnection(
      { baseUrl: "http://localhost:8000", deviceLabel: "laptop", serverUp: false },
      { onSignOut: vi.fn() },
    );
    expect(allText(screen)).toContain(TEXT_SETTINGS_CONNECTION[4]);
    expect(allText(screen)).not.toContain(TEXT_SETTINGS_CONNECTION[6]);
  });
});

describe("sign-out confirm", () => {
  it("names the unsynced count when marks wait", () => {
    const screen = renderSignOutConfirm({ unsynced: 5, failed: false }, { onConfirm: vi.fn(), onCancel: vi.fn() });
    expect(allText(screen)).toContain("5 marks are not synced.");
    expect(allText(screen)).not.toContain("Could not sign out.");
  });

  it("shows the live count with the inventory copy for one unsynced mark", () => {
    const screen = renderSignOutConfirm({ unsynced: 1, failed: false }, { onConfirm: vi.fn(), onCancel: vi.fn() });
    expect(allText(screen)).toContain("1 marks are not synced.");
  });

  it("hides the unsynced note with no marks waiting and shows the failure", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const screen = renderSignOutConfirm({ unsynced: 0, failed: true }, { onConfirm, onCancel });
    expect(allText(screen)).not.toContain("not synced");
    expect(allText(screen)).toContain(TEXT_SIGNOUT_CONFIRM[4]);
    buttonNamed(screen, TEXT_SIGNOUT_CONFIRM[2]).click();
    buttonNamed(screen, TEXT_SIGNOUT_CONFIRM[3]).click();
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("catches a rejected confirm without an unhandled rejection", async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error("down"));
    const screen = renderSignOutConfirm({ unsynced: 0, failed: false }, { onConfirm, onCancel: vi.fn() });
    buttonNamed(screen, TEXT_SIGNOUT_CONFIRM[2]).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

describe("settings sites", () => {
  it("shows the empty line with no sites", () => {
    const screen = renderSettingsSites({ sites: [] }, { onRemove: vi.fn() });
    expect(allText(screen)).toContain(TEXT_SETTINGS_SITES[4]);
  });

  it("removes a site through its Remove button", () => {
    const onRemove = vi.fn();
    const screen = renderSettingsSites({ sites: ["example.org"] }, { onRemove });
    expect(allText(screen)).toContain(TEXT_SETTINGS_SITES[1]);
    buttonNamed(screen, TEXT_SETTINGS_SITES[2]).click();
    expect(onRemove).toHaveBeenCalledWith("example.org");
  });
});

describe("settings jokes", () => {
  it("shows the switch state and the source", () => {
    const onToggle = vi.fn();
    const screen = renderSettingsJokes({ enabled: true, source: "kata" }, { onToggle });
    expect(allText(screen)).toContain(TEXT_SETTINGS_JOKES[1]);
    expect(allText(screen)).toContain(`${TEXT_SETTINGS_JOKES[2]} ${TEXT_SETTINGS_JOKES[3]}`);
    expect(allText(screen)).toContain("kata");
    const box = screen.querySelector<HTMLInputElement>("input[type=checkbox]");
    expect(box?.checked).toBe(true);
    if (box === null) throw new Error("no checkbox");
    box.checked = false;
    box.dispatchEvent(new Event("change"));
    expect(onToggle).toHaveBeenCalledWith(false);
  });
});

describe("settings appearance", () => {
  it("marks the chosen theme as pressed and reports the pick", () => {
    const onTheme = vi.fn();
    const screen = renderSettingsAppearance({ theme: "dark" }, { onTheme });
    expect(allText(screen)).toContain(TEXT_SETTINGS_APPEARANCE[1]);
    expect(buttonNamed(screen, TEXT_SETTINGS_APPEARANCE[3]).getAttribute("aria-pressed")).toBe("true");
    expect(buttonNamed(screen, TEXT_SETTINGS_APPEARANCE[2]).getAttribute("aria-pressed")).toBe("false");
    buttonNamed(screen, TEXT_SETTINGS_APPEARANCE[4]).click();
    expect(onTheme).toHaveBeenCalledWith("system");
  });
});

describe("settings allowed sources", () => {
  it("lists both tiers with their notes and the add form", () => {
    const screen = renderSettingsAllowlist(
      { tier1: ["docs.example"], tier2: ["blog.example"] },
      { onAdd: vi.fn(), onPromote: vi.fn(), onRemove: vi.fn() },
    );
    expect(allText(screen)).toContain(TEXT_SETTINGS_ALLOWLIST[1]);
    expect(allText(screen)).toContain(TEXT_SETTINGS_ALLOWLIST[2]);
    expect(allText(screen)).toContain(TEXT_SETTINGS_ALLOWLIST[3]);
    expect(allText(screen)).toContain(TEXT_SETTINGS_ALLOWLIST[5]);
    expect(allText(screen)).toContain(TEXT_SETTINGS_ALLOWLIST[8]);
  });

  it("offers Make Tier 1 only on Tier 2 rows and passes the domain on", () => {
    const onPromote = vi.fn();
    const onRemove = vi.fn();
    const screen = renderSettingsAllowlist(
      { tier1: ["docs.example"], tier2: ["blog.example"] },
      { onAdd: vi.fn(), onPromote, onRemove },
    );
    expect(screen.querySelectorAll(".make-tier1")).toHaveLength(1);
    buttonNamed(screen, TEXT_SETTINGS_ALLOWLIST[6]).click();
    expect(onPromote).toHaveBeenCalledWith("blog.example");
    expect(screen.querySelectorAll(".remove-domain")).toHaveLength(2);
    screen.querySelector<HTMLButtonElement>(".remove-domain")?.click();
    expect(onRemove).toHaveBeenCalledWith("docs.example");
  });

  it("adds the trimmed domain from the form", () => {
    const onAdd = vi.fn();
    const screen = renderSettingsAllowlist({ tier1: [], tier2: [] }, { onAdd, onPromote: vi.fn(), onRemove: vi.fn() });
    const input = screen.querySelector<HTMLInputElement>("form input");
    if (input === null) throw new Error("no input");
    input.value = "  new.example ";
    screen.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(onAdd).toHaveBeenCalledWith("new.example");
  });

  it("ignores an empty or blank add-domain submit", () => {
    const onAdd = vi.fn();
    const screen = renderSettingsAllowlist({ tier1: [], tier2: [] }, { onAdd, onPromote: vi.fn(), onRemove: vi.fn() });
    const input = screen.querySelector<HTMLInputElement>("form input");
    if (input === null) throw new Error("no input");
    input.value = "   ";
    screen.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(onAdd).not.toHaveBeenCalled();
  });
});

describe("ignored list", () => {
  it("shows the empty line when nothing is ignored", () => {
    const screen = renderIgnoredList({ rows: [] }, { onRestore: vi.fn(), onUndo: vi.fn() });
    expect(allText(screen)).toContain(TEXT_IGNORED_LIST[2]);
    expect(allText(screen)).toContain(TEXT_IGNORED_LIST[1]);
  });

  it("restores a row and shows Restored. with Undo for that concept", () => {
    const onRestore = vi.fn();
    const onUndo = vi.fn();
    const row = { conceptId: 4, label: "decimals", kind: "word" as const };
    const screen = renderIgnoredList({ rows: [row] }, { onRestore, onUndo });
    expect(allText(screen)).toContain(TEXT_IGNORED_LIST[6]);
    buttonNamed(screen, TEXT_IGNORED_LIST[3]).click();
    expect(onRestore).toHaveBeenCalledWith(4);

    const after = renderIgnoredList({ rows: [], restored: row }, { onRestore, onUndo });
    expect(allText(after)).toContain(`${TEXT_IGNORED_LIST[7]} decimals`);
    buttonNamed(after, "Undo").click();
    expect(onUndo).toHaveBeenCalledWith(4);
  });

  it("reaches the core client: Restore unignores, Undo ignores again", async () => {
    const client = { ignoreConcept: vi.fn().mockResolvedValue(undefined), unignoreConcept: vi.fn().mockResolvedValue(undefined) };
    const onChanged = vi.fn();
    const handlers = ignoredClientHandlers(client, onChanged);
    await handlers.onRestore(4);
    expect(client.unignoreConcept).toHaveBeenCalledWith(4);
    expect(client.ignoreConcept).not.toHaveBeenCalled();
    expect(onChanged).toHaveBeenLastCalledWith("restore", 4);
    await handlers.onUndo(4);
    expect(client.ignoreConcept).toHaveBeenCalledWith(4);
    expect(onChanged).toHaveBeenLastCalledWith("undo", 4);
  });

  it("does not report a change when the client call fails", async () => {
    const client = { ignoreConcept: vi.fn(), unignoreConcept: vi.fn().mockRejectedValue(new Error("down")) };
    const onChanged = vi.fn();
    await expect(ignoredClientHandlers(client, onChanged).onRestore(4)).rejects.toThrow("down");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("keeps the row when the Restore handler rejects, without an unhandled rejection", async () => {
    const onRestore = vi.fn().mockRejectedValue(new Error("down"));
    const row = { conceptId: 4, label: "decimals", kind: "word" as const };
    const screen = renderIgnoredList({ rows: [row] }, { onRestore, onUndo: vi.fn() });
    buttonNamed(screen, TEXT_IGNORED_LIST[3]).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onRestore).toHaveBeenCalledWith(4);
    expect(allText(screen)).toContain("decimals");
    expect(allText(screen)).not.toContain(TEXT_IGNORED_LIST[7]);
  });

  it("keeps the Restored line when the Undo handler rejects, without an unhandled rejection", async () => {
    const onUndo = vi.fn().mockRejectedValue(new Error("down"));
    const row = { conceptId: 4, label: "decimals", kind: "word" as const };
    const screen = renderIgnoredList({ rows: [], restored: row }, { onRestore: vi.fn(), onUndo });
    buttonNamed(screen, TEXT_PIN[6]).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onUndo).toHaveBeenCalledWith(4);
    expect(allText(screen)).toContain(`${TEXT_IGNORED_LIST[7]} decimals`);
  });

  it("logs a failing redraw after a successful core call instead of failing the Restore", async () => {
    const client = { ignoreConcept: vi.fn(), unignoreConcept: vi.fn().mockResolvedValue(undefined) };
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const onChanged = vi.fn().mockImplementation(() => {
      throw new Error("redraw");
    });
    try {
      await expect(ignoredClientHandlers(client, onChanged).onRestore(4)).resolves.toBeUndefined();
      expect(error).toHaveBeenCalledOnce();
    } finally {
      error.mockRestore();
    }
  });

  it("shows Back only with a handler", () => {
    const onBack = vi.fn();
    const screen = renderIgnoredList({ rows: [] }, { onRestore: vi.fn(), onUndo: vi.fn(), onBack });
    buttonNamed(screen, TEXT_IGNORED_LIST[4]).click();
    expect(onBack).toHaveBeenCalledOnce();
    const bare = renderIgnoredList({ rows: [] }, { onRestore: vi.fn(), onUndo: vi.fn() });
    expect(bare.querySelector(".back")).toBeNull();
  });
});
