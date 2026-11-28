import { describe, expect, it, vi } from "vitest";
import { type ConceptAction, renderBlockMenu, renderConceptActions } from "../src/ui/overlay/blockMenu";
import { renderImageMenu } from "../src/ui/overlay/imageMenu";
import { renderListPicker } from "../src/ui/overlay/listPicker";
import { TEXT_BLOCK_MENU, TEXT_IMAGE_PIN_MENU, TEXT_LIST_PICKER, TEXT_PIN, TEXT_REVIEW } from "../src/ui/strings";
import type { Clock } from "../src/ui/undo";

const STATES = ["empty", "loading", "error", "offline"] as const;

/** Timer source a test fires by hand. */
function fakeClock(): Clock & { fire(): void; pendingCount(): number } {
  const timers = new Map<number, () => void>();
  let next = 1;
  return {
    setTimeout(run) {
      const handle = next++;
      timers.set(handle, run);
      return handle;
    },
    clearTimeout(handle) {
      timers.delete(handle);
    },
    fire() {
      const runs = [...timers.values()];
      timers.clear();
      for (const run of runs) run();
    },
    pendingCount: () => timers.size,
  };
}

/** Lets the confirm promise settle. */
async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function buttonLabels(root: HTMLElement): string[] {
  return [...root.querySelectorAll("button")].map((b) => b.textContent ?? "");
}

function statusText(root: HTMLElement): string {
  return root.querySelector(".menu-status")?.textContent ?? "";
}

describe("block menu", () => {
  it("renders the inventory heading, bulk labels and notes", () => {
    const menu = renderBlockMenu(document, "ready", { onBulk: vi.fn() });
    expect(menu.querySelector("h2")?.textContent).toBe(TEXT_BLOCK_MENU[5]);
    expect(buttonLabels(menu)).toEqual([TEXT_BLOCK_MENU[0], TEXT_BLOCK_MENU[1], TEXT_BLOCK_MENU[2], TEXT_BLOCK_MENU[3]]);
    const notes = [...menu.querySelectorAll(".menu-note")].map((p) => p.textContent);
    expect(notes).toEqual([TEXT_BLOCK_MENU[4], TEXT_BLOCK_MENU[6]]);
    expect(statusText(menu)).toBe("");
  });

  it("hides the bulk buttons until onBulk is wired", () => {
    const menu = renderBlockMenu(document, "ready", {});
    expect(menu.querySelector(".menu-list")).toBeNull();
    expect(menu.querySelectorAll("button")).toHaveLength(0);
    expect(menu.querySelector("h2")?.textContent).toBe(TEXT_BLOCK_MENU[5]);
  });

  it("shows the empty, error and offline line and disables buttons while loading", () => {
    expect(statusText(renderBlockMenu(document, "empty", { onBulk: vi.fn() }))).toBe(TEXT_REVIEW[19]);
    expect(statusText(renderBlockMenu(document, "error", { onBulk: vi.fn() }))).toBe(TEXT_REVIEW[20]);
    expect(statusText(renderBlockMenu(document, "offline", { onBulk: vi.fn() }))).toBe(TEXT_PIN[4]);
    const loading = renderBlockMenu(document, "loading", { onBulk: vi.fn() });
    expect(statusText(loading)).toBe("");
    expect([...loading.querySelectorAll("button")].every((b) => b.disabled)).toBe(true);
  });

  it("a bulk button passes its inventory label to onBulk", () => {
    const onBulk = vi.fn();
    const menu = renderBlockMenu(document, "ready", { onBulk });
    [...menu.querySelectorAll("button")][1].click();
    expect(onBulk).toHaveBeenCalledWith(TEXT_BLOCK_MENU[1]);
  });
});

describe("image pin menu", () => {
  it("renders the inventory heading, note and action labels", () => {
    const menu = renderImageMenu(document, "ready", { onPick: vi.fn() });
    expect(menu.querySelector("h2")?.textContent).toBe(TEXT_IMAGE_PIN_MENU[3]);
    expect(menu.querySelector(".menu-note")?.textContent).toBe(TEXT_IMAGE_PIN_MENU[2]);
    expect(buttonLabels(menu)).toEqual([0, 1, 4, 5, 6, 7, 8, 9].map((i) => TEXT_IMAGE_PIN_MENU[i]));
  });

  it.each(STATES.filter((s) => s !== "loading"))("%s state shows its line", (state) => {
    const menu = renderImageMenu(document, state, { onPick: vi.fn() });
    const expected = { empty: TEXT_REVIEW[19], error: TEXT_IMAGE_PIN_MENU[10], offline: TEXT_PIN[4] }[state];
    expect(statusText(menu)).toBe(expected);
  });

  it("loading disables every button and shows no line", () => {
    const menu = renderImageMenu(document, "loading", { onPick: vi.fn() });
    expect(statusText(menu)).toBe("");
    expect([...menu.querySelectorAll("button")].every((b) => b.disabled)).toBe(true);
  });

  it("a button passes its label to onPick", () => {
    const onPick = vi.fn();
    const menu = renderImageMenu(document, "ready", { onPick });
    [...menu.querySelectorAll("button")][0].click();
    expect(onPick).toHaveBeenCalledWith(TEXT_IMAGE_PIN_MENU[0]);
  });
});

describe("list picker", () => {
  const lists = ["Networking basics", "Algebra"];

  it("renders the lists, New list and Cancel on the ready state", () => {
    const card = renderListPicker(document, "ready", lists, { onPick: vi.fn(), onNew: vi.fn(), onCancel: vi.fn() });
    expect(card.querySelector("h2")?.textContent).toBe(TEXT_LIST_PICKER[0]);
    expect(card.querySelector("p")?.textContent).toBe(TEXT_LIST_PICKER[1]);
    expect(buttonLabels(card)).toEqual([...lists, TEXT_LIST_PICKER[3], TEXT_LIST_PICKER[5]]);
    expect(statusText(card)).toBe("");
  });

  it("empty state shows the no-lists line and only New list and Cancel", () => {
    const card = renderListPicker(document, "empty", lists, { onPick: vi.fn(), onNew: vi.fn(), onCancel: vi.fn() });
    expect(statusText(card)).toBe(TEXT_LIST_PICKER[2]);
    expect(buttonLabels(card)).toEqual([TEXT_LIST_PICKER[3], TEXT_LIST_PICKER[5]]);
  });

  it("error state shows the load failure line", () => {
    const card = renderListPicker(document, "error", [], { onPick: vi.fn(), onNew: vi.fn(), onCancel: vi.fn() });
    expect(statusText(card)).toBe(TEXT_LIST_PICKER[6]);
  });

  it("offline state shows the server line", () => {
    const card = renderListPicker(document, "offline", [], { onPick: vi.fn(), onNew: vi.fn(), onCancel: vi.fn() });
    expect(statusText(card)).toBe(TEXT_PIN[4]);
  });

  it("loading disables New list and shows no lists", () => {
    const card = renderListPicker(document, "loading", lists, { onPick: vi.fn(), onNew: vi.fn(), onCancel: vi.fn() });
    expect(buttonLabels(card)).toEqual([TEXT_LIST_PICKER[3], TEXT_LIST_PICKER[5]]);
    expect(card.querySelector<HTMLButtonElement>(".list-picker-new")?.disabled).toBe(true);
    expect(statusText(card)).toBe("");
  });

  it("buttons call onPick, onNew and onCancel", () => {
    const actions = { onPick: vi.fn(), onNew: vi.fn(), onCancel: vi.fn() };
    const card = renderListPicker(document, "ready", lists, actions);
    [...card.querySelectorAll("button")][1].click();
    card.querySelector<HTMLButtonElement>(".list-picker-new")?.click();
    card.querySelector<HTMLButtonElement>(".list-picker-cancel")?.click();
    expect(actions.onPick).toHaveBeenCalledWith("Algebra");
    expect(actions.onNew).toHaveBeenCalledTimes(1);
    expect(actions.onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("concept Delete and Ignore", () => {
  /** Clicks the action, then confirms or cancels the confirm box. */
  async function clickAction(box: HTMLElement, cls: string, confirm: boolean): Promise<void> {
    box.querySelector<HTMLButtonElement>(cls)?.click();
    await flush();
    box.querySelector<HTMLButtonElement>(confirm ? ".confirm-yes" : ".confirm-no")?.click();
    await flush();
  }

  it.each([
    [".concept-delete", "delete", TEXT_REVIEW[29]],
    [".concept-ignore", "ignore", TEXT_REVIEW[30]],
  ] as const)("%s asks confirm first, then commits after one Undo window", async (cls, action: ConceptAction, yes) => {
    const clock = fakeClock();
    const onCommit = vi.fn();
    const box = renderConceptActions(document, { windowMs: 5000, clock, onCommit });
    box.querySelector<HTMLButtonElement>(cls)?.click();
    await flush();
    expect(box.querySelector(".confirm-message")).not.toBeNull();
    expect(box.querySelector(".confirm-yes")?.textContent).toBe(yes);
    box.querySelector<HTMLButtonElement>(".confirm-yes")?.click();
    await flush();
    expect(onCommit).not.toHaveBeenCalled();
    expect(box.querySelectorAll(".concept-undo")).toHaveLength(1);
    clock.fire();
    expect(onCommit).toHaveBeenCalledWith(action);
    expect(box.querySelector(".concept-undo")).toBeNull();
  });

  it("Undo before the window cancels the commit", async () => {
    const clock = fakeClock();
    const onCommit = vi.fn();
    const box = renderConceptActions(document, { windowMs: 5000, clock, onCommit });
    await clickAction(box, ".concept-delete", true);
    const undo = box.querySelector<HTMLButtonElement>(".concept-undo");
    expect(undo?.textContent).toBe(TEXT_PIN[6]);
    undo?.click();
    clock.fire();
    expect(onCommit).not.toHaveBeenCalled();
    expect(box.querySelector(".concept-undo")).toBeNull();
  });

  it("Cancel in the confirm keeps the concept and offers no Undo", async () => {
    const clock = fakeClock();
    const onCommit = vi.fn();
    const box = renderConceptActions(document, { windowMs: 5000, clock, onCommit });
    await clickAction(box, ".concept-ignore", false);
    expect(box.querySelector(".concept-undo")).toBeNull();
    expect(clock.pendingCount()).toBe(0);
    expect(onCommit).not.toHaveBeenCalled();
  });
});
