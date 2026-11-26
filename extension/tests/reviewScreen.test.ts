import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderReview, type ReviewHandlers, type ReviewRow } from "../src/reviewScreen";

function handlers(overrides: Partial<ReviewHandlers> = {}): ReviewHandlers {
  return { onSet: vi.fn(async () => undefined), ...overrides };
}

function row(conceptId: number, label: string, state: ReviewRow["state"] = null, extra: Partial<ReviewRow> = {}): ReviewRow {
  return { conceptId, label, state, evidence: "", ...extra };
}

/** Button of the toolbar or a row by its visible text. */
function byText(scope: Element, text: string): HTMLButtonElement {
  const found = buttons(scope).find((b) => b.textContent === text);
  if (!found) throw new Error(`no button ${text}`);
  return found;
}

function rowButtons(item: Element): HTMLButtonElement[] {
  return [...item.querySelectorAll(".state-menu button")] as HTMLButtonElement[];
}

function labels(): (string | null | undefined)[] {
  return [...root.querySelectorAll(".label")].map((n) => n.textContent);
}

const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

function buttons(item: Element): HTMLButtonElement[] {
  return [...item.querySelectorAll("button")];
}

function pressed(item: Element): (string | null)[] {
  return rowButtons(item).map((b) => b.getAttribute("aria-pressed"));
}

function key(target: Element, k: string): void {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
}

let root: HTMLElement;

describe("renderReview", () => {
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
      ["false", "false", "true"],
      ["false", "true", "false"],
      ["true", "false", "false"],
      ["false", "false", "false"],
    ]);
    expect(items[0].querySelector('[role="group"]')?.getAttribute("aria-label")).toBeTruthy();
    expect(rowButtons(items[0]).map((b) => b.textContent)).toEqual(["New", "Learning", "Known"]);
  });

  it("click calls onSet and updates aria-pressed", async () => {
    const h = handlers();
    renderReview(root, [row(7, "a")], h);
    rowButtons(root)[1].click();
    await flush();
    expect(h.onSet).toHaveBeenCalledWith(7, "learning");
    expect(pressed(root)).toEqual(["false", "true", "false"]);
  });

  it("shows the error, keeps state and re-enables buttons", async () => {
    const h = handlers({ onSet: vi.fn(async () => Promise.reject(new Error("x"))) });
    renderReview(root, [row(1, "a", "known")], h);
    rowButtons(root)[0].click();
    await flush();
    expect(root.querySelector(".state-menu .note")?.textContent).toBe("x");
    expect(pressed(root)).toEqual(["false", "false", "true"]);
    expect(rowButtons(root).every((b) => !b.disabled)).toBe(true);
  });

  it("moves focus between rows with ArrowDown and ArrowUp", () => {
    renderReview(root, [row(1, "a"), row(2, "b")], handlers());
    const items = [...root.querySelectorAll("li")];
    rowButtons(items[0])[1].focus();
    key(rowButtons(items[0])[1], "ArrowDown");
    expect(document.activeElement).toBe(rowButtons(items[1])[0]);
    key(rowButtons(items[1])[0], "ArrowUp");
    expect(document.activeElement).toBe(rowButtons(items[0])[0]);
  });

  it("sets known, learning, new with keys 1, 2, 3", async () => {
    const h = handlers();
    renderReview(root, [row(9, "a")], h);
    const first = rowButtons(root)[0];
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
    const first = rowButtons(root)[0];
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

  it("starts with every area collapsed and shows counts", () => {
    renderReview(
      root,
      [row(1, "a", "known", { area: "Math" }), row(2, "b", "new", { area: "Math" }), row(3, "c", "new", { area: "Art" })],
      handlers(),
    );
    const areas = [...root.querySelectorAll("details")];
    expect(areas.map((d) => d.open)).toEqual([false, false]);
    expect(areas[0].querySelector("summary")?.textContent).toBe("Math (2) New 1, Learning 0, Known 1");
  });

  it("Expand all and Collapse all toggle every area", () => {
    renderReview(root, [row(1, "a", null, { area: "Math" }), row(2, "b", null, { area: "Art" })], handlers());
    byText(root, "Expand all").click();
    expect([...root.querySelectorAll("details")].every((d) => d.open)).toBe(true);
    byText(root, "Collapse all").click();
    expect([...root.querySelectorAll("details")].some((d) => d.open)).toBe(false);
  });

  it("search narrows the rows", () => {
    renderReview(root, [row(1, "Alpha"), row(2, "Beta")], handlers());
    const input = root.querySelector("input[type=search]") as HTMLInputElement;
    input.value = "bet";
    input.dispatchEvent(new Event("input"));
    expect(labels()).toEqual(["Beta"]);
    expect(root.querySelector(".review-total")?.textContent).toBe("1 of 2 concepts");
  });

  it.each([
    ["New", ["n"]],
    ["Learning", ["l"]],
    ["Known", ["k"]],
  ])("state filter %s narrows the rows", (name, expected) => {
    renderReview(root, [row(1, "n", "new"), row(2, "l", "learning"), row(3, "k", "known")], handlers());
    const filterButton = byText(root.querySelector(".review-toolbar") as Element, name);
    filterButton.click();
    expect(filterButton.getAttribute("aria-pressed")).toBe("true");
    expect(labels()).toEqual(expected);
  });

  it("a saved state survives a redraw from search", async () => {
    renderReview(root, [row(1, "a", "new")], handlers());
    const details = root.querySelector("details") as HTMLDetailsElement;
    details.open = true;
    byText(root.querySelector(".review-tree") as Element, "Known").click();
    await flush();
    const input = root.querySelector("input[type=search]") as HTMLInputElement;
    input.value = "a";
    input.dispatchEvent(new Event("input"));
    expect(pressed(root.querySelector("li") as Element)).toEqual(["false", "false", "true"]);
  });

  it("does not mutate the caller's rows when a state is saved", async () => {
    const rows = [row(1, "a", "new")];
    renderReview(root, rows, handlers());
    (root.querySelector("details") as HTMLDetailsElement).open = true;
    byText(root.querySelector(".review-tree") as Element, "Known").click();
    await flush();
    expect(rows[0]?.state).toBe("new");
  });

  it("a failed keyboard save shows the error in the row note and reverts", async () => {
    const onSet = vi.fn(async () => {
      throw new Error("save failed");
    });
    renderReview(root, [row(1, "a", "new")], handlers({ onSet }));
    const item = root.querySelector("li") as Element;
    key(item, "1");
    await flush();
    expect(item.querySelector(".note")?.textContent).toBe("save failed");
    expect(pressed(item)).toEqual(["true", "false", "false"]);
  });

  it("Only this page keeps rows of the page", () => {
    renderReview(root, [row(1, "on", null, { onPage: true }), row(2, "off", null, { onPage: false })], handlers());
    const box = root.querySelector(".only-page input") as HTMLInputElement;
    box.checked = true;
    box.dispatchEvent(new Event("change"));
    expect(labels()).toEqual(["on"]);
  });
});
