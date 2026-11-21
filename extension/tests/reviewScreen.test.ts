import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderReview, type ReviewHandlers, type ReviewRow } from "../src/reviewScreen";

function handlers(overrides: Partial<ReviewHandlers> = {}): ReviewHandlers {
  return { onSet: vi.fn(async () => undefined), ...overrides };
}

function row(conceptId: number, label: string, state: ReviewRow["state"] = null): ReviewRow {
  return { conceptId, label, state, evidence: "" };
}

const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

function buttons(item: Element): HTMLButtonElement[] {
  return [...item.querySelectorAll("button")];
}

function pressed(item: Element): (string | null)[] {
  return buttons(item).map((b) => b.getAttribute("aria-pressed"));
}

function key(target: Element, k: string): void {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
}

describe("renderReview", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("renders each state as pressed and null as none", () => {
    renderReview(
      root,
      [row(1, "a", "known"), row(2, "b", "learning"), row(3, "c", "new"), row(4, "d", null)],
      handlers(),
    );
    const items = [...root.querySelectorAll("li")];
    expect(items.map(pressed)).toEqual([
      ["true", "false", "false"],
      ["false", "true", "false"],
      ["false", "false", "true"],
      ["false", "false", "false"],
    ]);
    expect(items[0].querySelector('[role="group"]')?.getAttribute("aria-label")).toBeTruthy();
    expect(buttons(items[0]).map((b) => b.textContent)).toEqual(["known", "learning", "new"]);
  });

  it("click calls onSet and updates aria-pressed", async () => {
    const h = handlers();
    renderReview(root, [row(7, "a")], h);
    buttons(root)[1].click();
    await flush();
    expect(h.onSet).toHaveBeenCalledWith(7, "learning");
    expect(pressed(root)).toEqual(["false", "true", "false"]);
    expect(root.querySelector(".note")?.textContent).toBe("saved");
  });

  it("shows failed, keeps state and re-enables buttons", async () => {
    const h = handlers({ onSet: vi.fn(async () => Promise.reject(new Error("x"))) });
    renderReview(root, [row(1, "a", "known")], h);
    buttons(root)[2].click();
    await flush();
    expect(root.querySelector(".note")?.textContent).toBe("failed");
    expect(pressed(root)).toEqual(["true", "false", "false"]);
    expect(buttons(root).every((b) => !b.disabled)).toBe(true);
  });

  it("moves focus between rows with ArrowDown and ArrowUp", () => {
    renderReview(root, [row(1, "a"), row(2, "b")], handlers());
    const items = [...root.querySelectorAll("li")];
    buttons(items[0])[1].focus();
    key(buttons(items[0])[1], "ArrowDown");
    expect(document.activeElement).toBe(buttons(items[1])[0]);
    key(buttons(items[1])[0], "ArrowUp");
    expect(document.activeElement).toBe(buttons(items[0])[0]);
  });

  it("sets known, learning, new with keys 1, 2, 3", async () => {
    const h = handlers();
    renderReview(root, [row(9, "a")], h);
    const first = buttons(root)[0];
    for (const k of ["1", "2", "3"]) {
      key(first, k);
      await flush();
    }
    expect(vi.mocked(h.onSet).mock.calls).toEqual([
      [9, "known"],
      [9, "learning"],
      [9, "new"],
    ]);
  });

  it("ignores keys while a save is in flight", async () => {
    let release: () => void = () => undefined;
    const h = handlers({
      onSet: vi.fn(() => new Promise<void>((resolve) => (release = resolve))),
    });
    renderReview(root, [row(1, "a")], h);
    const first = buttons(root)[0];
    key(first, "1");
    key(first, "2");
    expect(h.onSet).toHaveBeenCalledTimes(1);
    release();
    await flush();
    key(first, "2");
    expect(h.onSet).toHaveBeenCalledTimes(2);
  });

  it("shows text for an empty list", () => {
    renderReview(root, [], handlers());
    expect(root.querySelector("p")?.textContent).toBe("No concepts to review");
    expect(root.querySelector("li")).toBeNull();
  });

  it("keeps markup in a label as text", () => {
    renderReview(root, [row(1, "<b>bold</b>")], handlers());
    expect(root.querySelector("b")).toBeNull();
    expect(root.querySelector(".label")?.textContent).toBe("<b>bold</b>");
  });
});
