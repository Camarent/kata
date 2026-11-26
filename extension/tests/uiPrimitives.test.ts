import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { askConfirm } from "../src/ui/confirm";
import { el } from "../src/ui/dom";
import { createPopover } from "../src/ui/popover";
import { renderStateMenu } from "../src/ui/stateMenu";
import { type Clock, deferCommit } from "../src/ui/undo";

const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

function key(target: EventTarget, k: string): void {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
}

/** Clock the test moves by hand: advance(ms) runs every timer that is due. */
function manualClock(): Clock & { advance(ms: number): void; pendingCount(): number } {
  let now = 0;
  let nextHandle = 1;
  const timers = new Map<number, { due: number; run: () => void }>();
  return {
    setTimeout(run, ms) {
      const handle = nextHandle++;
      timers.set(handle, { due: now + ms, run });
      return handle;
    },
    clearTimeout(handle) {
      timers.delete(handle);
    },
    advance(ms) {
      now += ms;
      for (const [handle, timer] of [...timers]) {
        if (timer.due <= now && timers.delete(handle)) timer.run();
      }
    },
    pendingCount: () => timers.size,
  };
}

describe("el", () => {
  it("sets text and class without parsing markup", () => {
    const node = el("span", "<b>x</b>", "cls");
    expect(node.textContent).toBe("<b>x</b>");
    expect(node.querySelector("b")).toBeNull();
    expect(node.className).toBe("cls");
  });
});

describe("renderStateMenu", () => {
  it("renders New, Learning, Known in order and marks the current state", () => {
    const menu = renderStateMenu("learning", vi.fn());
    const buttons = [...menu.querySelectorAll("button")];
    expect(buttons.map((b) => b.textContent)).toEqual(["New", "Learning", "Known"]);
    expect(buttons.map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]);
  });

  it("marks no state when current is null and passes the chosen state on click", () => {
    const onChoose = vi.fn();
    const menu = renderStateMenu(null, onChoose);
    const buttons = [...menu.querySelectorAll("button")];
    expect(buttons.map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "false", "false"]);
    buttons[2].click();
    expect(onChoose).toHaveBeenCalledWith("known");
  });

  it("shows the message when the chosen state rejects", async () => {
    const onChoose = vi.fn(() => Promise.reject(new Error("save failed")));
    const menu = renderStateMenu(null, onChoose);
    menu.querySelector<HTMLButtonElement>("button")?.click();
    await flush();
    expect(menu.querySelector(".note")?.textContent).toBe("save failed");
  });

  it("ignores the error of a click that a later click superseded", async () => {
    let rejectSlow: (err: Error) => void = () => {};
    const onChoose = vi.fn((state: string) =>
      state === "known"
        ? new Promise<void>((_, reject) => {
            rejectSlow = reject;
          })
        : Promise.resolve(),
    );
    const menu = renderStateMenu(null, onChoose);
    const buttons = [...menu.querySelectorAll<HTMLButtonElement>("button")];
    buttons[2].click();
    buttons[0].click();
    await flush();
    rejectSlow(new Error("save failed"));
    await flush();
    expect(menu.querySelector(".note")?.textContent).toBe("");
  });
});

describe("askConfirm", () => {
  let host: HTMLElement;

  beforeEach(() => {
    host = document.createElement("div");
    document.body.append(host);
  });

  afterEach(() => {
    host.remove();
  });

  it("resolves true on confirm and removes its box", async () => {
    const result = askConfirm(host, { message: "Delete course?", confirmLabel: "Delete" });
    host.querySelector<HTMLButtonElement>(".confirm-yes")?.click();
    await expect(result).resolves.toBe(true);
    expect(host.querySelector(".confirm")).toBeNull();
  });

  it("resolves false on cancel and removes its box", async () => {
    const result = askConfirm(host, { message: "Ignore concept?", confirmLabel: "Ignore" });
    expect(host.querySelector(".confirm-message")?.textContent).toBe("Ignore concept?");
    host.querySelector<HTMLButtonElement>(".confirm-no")?.click();
    await expect(result).resolves.toBe(false);
    expect(host.querySelector(".confirm")).toBeNull();
  });
});

describe("deferCommit", () => {
  it("runs commit after the window when not undone", () => {
    const clock = manualClock();
    const commit = vi.fn();
    const pending = deferCommit(commit, 5000, clock);
    clock.advance(4999);
    expect(commit).not.toHaveBeenCalled();
    clock.advance(1);
    expect(commit).toHaveBeenCalledTimes(1);
    expect(pending.pending).toBe(false);
    expect(pending.undo()).toBe(false);
  });

  it("undo cancels the commit and runs once", () => {
    const clock = manualClock();
    const commit = vi.fn();
    const pending = deferCommit(commit, 5000, clock);
    expect(pending.undo()).toBe(true);
    expect(pending.undo()).toBe(false);
    expect(clock.pendingCount()).toBe(0);
    clock.advance(10000);
    expect(commit).not.toHaveBeenCalled();
    expect(clock.pendingCount()).toBe(0);
  });

  it("undo after the timeout does nothing", () => {
    const clock = manualClock();
    const commit = vi.fn();
    const pending = deferCommit(commit, 1000, clock);
    clock.advance(1000);
    expect(pending.undo()).toBe(false);
    expect(commit).toHaveBeenCalledTimes(1);
  });
});

describe("createPopover", () => {
  let anchor: HTMLButtonElement;
  let outside: HTMLButtonElement;

  beforeEach(() => {
    anchor = document.createElement("button");
    outside = document.createElement("button");
    document.body.append(anchor, outside);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    anchor.remove();
    outside.remove();
  });

  it("starts hidden and shows on open", () => {
    const popover = createPopover(anchor, el("p", "details"));
    expect(popover.element.hidden).toBe(true);
    popover.open();
    expect(popover.isOpen).toBe(true);
    expect(popover.element.hidden).toBe(false);
    popover.close();
  });

  it("closes on Escape", () => {
    const popover = createPopover(anchor, el("p", "details"));
    popover.open();
    key(document, "Escape");
    expect(popover.isOpen).toBe(false);
    expect(popover.element.hidden).toBe(true);
  });

  it("closes on a click outside the popover and anchor", () => {
    const popover = createPopover(anchor, el("p", "details"));
    document.body.append(popover.element);
    popover.open();
    outside.click();
    expect(popover.isOpen).toBe(false);
    popover.element.remove();
  });

  it("stays open on a click inside the popover or on the anchor", () => {
    const popover = createPopover(anchor, el("p", "details"));
    document.body.append(popover.element);
    popover.open();
    popover.element.querySelector("p")?.click();
    anchor.click();
    expect(popover.isOpen).toBe(true);
    popover.close();
    popover.element.remove();
  });

  it("removes its document listeners on close", () => {
    const popover = createPopover(anchor, el("p", "details"));
    const add = vi.spyOn(document, "addEventListener");
    const remove = vi.spyOn(document, "removeEventListener");
    popover.open();
    try {
      const keydown = add.mock.calls.find((c) => c[0] === "keydown")?.[1];
      const mousedown = add.mock.calls.find((c) => c[0] === "mousedown")?.[1];
      const click = add.mock.calls.find((c) => c[0] === "click")?.[1];
      popover.close();
      expect(remove).toHaveBeenCalledWith("keydown", keydown);
      expect(remove).toHaveBeenCalledWith("mousedown", mousedown, true);
      expect(remove).toHaveBeenCalledWith("click", click, true);
    } finally {
      popover.close();
    }
  });
});
