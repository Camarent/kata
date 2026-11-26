import { afterEach, describe, expect, it, vi } from "vitest";
import { renderListDelete } from "../src/ui/panel/listDelete";
import { renderListDetail, type ListDetailState } from "../src/ui/panel/listDetail";
import { renderListEdit, type ListEditError } from "../src/ui/panel/listEdit";
import { TEXT_LIST_DELETE, TEXT_LIST_DETAIL, TEXT_LIST_EDIT, TEXT_PIN } from "../src/ui/strings";
import type { Clock } from "../src/ui/undo";

const UNDO = TEXT_PIN[6];

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

/** Lets the confirm promise settle: askConfirm resolves in a few microtasks. */
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

/** The button with this label inside root, or throws. */
function buttonLabelled(root: HTMLElement, label: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((b) => b.textContent === label);
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}

/** Mounts a screen in the document so DOM queries and clicks work; removed after each test. */
function mount(screen: HTMLElement): HTMLElement {
  document.body.append(screen);
  return screen;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("list detail", () => {
  const readyProps = { name: "Week 1", state: "ready" as ListDetailState, concepts: ["Alpha", "Beta"] };

  it("ready: shows the name, the draft note and one row per concept with Remove", () => {
    const onRemove = vi.fn();
    const screen = mount(renderListDetail(readyProps, { onRemove }));
    expect(screen.querySelector("h3")?.textContent).toBe("Week 1");
    expect(screen.querySelector(".note")?.textContent).toBe(TEXT_LIST_DETAIL[1]);
    const rows = screen.querySelectorAll("li.concept");
    expect(rows).toHaveLength(2);
    expect(rows[1].querySelector(".label")?.textContent).toBe("Beta");
    buttonLabelled(rows[1] as HTMLElement, TEXT_LIST_DETAIL[4]).click();
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it("ready: Generate course is enabled", () => {
    const screen = mount(renderListDetail(readyProps, { onGenerate: vi.fn() }));
    expect(buttonLabelled(screen, TEXT_LIST_DETAIL[6]).disabled).toBe(false);
  });

  it("empty: shows the empty line, no concept rows, Generate course off", () => {
    const screen = mount(
      renderListDetail({ ...readyProps, state: "empty", concepts: [] }, { onGenerate: vi.fn() }),
    );
    expect(screen.querySelector(".empty")?.textContent).toBe(TEXT_LIST_DETAIL[8]);
    expect(screen.querySelector("ul.concepts")).toBeNull();
    expect(buttonLabelled(screen, TEXT_LIST_DETAIL[6]).disabled).toBe(true);
  });

  it("error: shows the load error line and no concept rows", () => {
    const screen = mount(renderListDetail({ ...readyProps, state: "error" }, {}));
    expect(screen.querySelector(".status")?.textContent).toBe(TEXT_LIST_DETAIL[9]);
    expect(screen.querySelector("li.concept")).toBeNull();
  });

  it("hides every action whose handler is absent", () => {
    const screen = mount(renderListDetail(readyProps, {}));
    const labels = [...screen.querySelectorAll("button")].map((b) => b.textContent);
    expect(labels).toEqual([]);
  });

  it("shows Rename, Add, Generate, Delete and Back when handlers are given, and each calls its handler", () => {
    const actions = {
      onRename: vi.fn(),
      onAddTopic: vi.fn(),
      onGenerate: vi.fn(),
      onDelete: vi.fn(),
      onBack: vi.fn(),
    };
    const screen = mount(renderListDetail(readyProps, actions));
    buttonLabelled(screen, TEXT_LIST_DETAIL[2]).click();
    buttonLabelled(screen, TEXT_LIST_DETAIL[5]).click();
    buttonLabelled(screen, TEXT_LIST_DETAIL[6]).click();
    buttonLabelled(screen, TEXT_LIST_DETAIL[3]).click();
    buttonLabelled(screen, TEXT_LIST_DETAIL[7]).click();
    expect(actions.onRename).toHaveBeenCalledOnce();
    expect(actions.onAddTopic).toHaveBeenCalledOnce();
    expect(actions.onGenerate).toHaveBeenCalledOnce();
    expect(actions.onDelete).toHaveBeenCalledOnce();
    expect(actions.onBack).toHaveBeenCalledOnce();
  });
});

describe("list edit", () => {
  const cases: Array<[ListEditError, string | null]> = [
    [null, null],
    ["save", TEXT_LIST_EDIT[3]],
    ["duplicate", TEXT_LIST_EDIT[4]],
  ];

  it.each(cases)("error %s: shows the matching line or none", (error, text) => {
    const screen = mount(renderListEdit({ name: "Week 1", error }, { onSave: vi.fn(), onCancel: vi.fn() }));
    expect(screen.querySelector(".label")?.textContent).toBe(TEXT_LIST_EDIT[0]);
    expect(screen.querySelector(".error")?.textContent ?? null).toBe(text);
  });

  it("starts with the current name in the field", () => {
    const screen = mount(renderListEdit({ name: "Week 1", error: null }, { onSave: vi.fn(), onCancel: vi.fn() }));
    expect((screen.querySelector("input") as HTMLInputElement).value).toBe("Week 1");
  });

  it("Save passes the typed name trimmed; Cancel calls onCancel", () => {
    const onSave = vi.fn();
    const onCancel = vi.fn();
    const screen = mount(renderListEdit({ name: "Week 1", error: null }, { onSave, onCancel }));
    (screen.querySelector("input") as HTMLInputElement).value = "  Week 2  ";
    buttonLabelled(screen, TEXT_LIST_EDIT[1]).click();
    buttonLabelled(screen, TEXT_LIST_EDIT[2]).click();
    expect(onSave).toHaveBeenCalledWith("Week 2");
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe("list delete", () => {
  it("shows the note and no error line by default", () => {
    const screen = mount(renderListDelete({ error: false }, { onDelete: vi.fn(), undoWindowMs: 5000 }));
    expect(screen.querySelector(".note")?.textContent).toBe(TEXT_LIST_DELETE[1]);
    expect(screen.querySelector(".error")).toBeNull();
  });

  it("shows the failure line after a failed delete", () => {
    const screen = mount(renderListDelete({ error: true }, { onDelete: vi.fn(), undoWindowMs: 5000 }));
    expect(screen.querySelector(".error")?.textContent).toBe(TEXT_LIST_DELETE[4]);
  });

  it("Delete asks for confirmation; Cancel in the confirm deletes nothing", async () => {
    const clock = fakeClock();
    const onDelete = vi.fn();
    const screen = mount(renderListDelete({ error: false }, { onDelete, undoWindowMs: 5000, clock }));
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    expect(screen.querySelector(".confirm-message")?.textContent).toBe(TEXT_LIST_DELETE[0]);
    (screen.querySelector(".confirm-no") as HTMLButtonElement).click();
    await settle();
    expect(screen.querySelector(".confirm")).toBeNull();
    expect(screen.querySelector(".undo")).toBeNull();
    clock.fire();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("confirmed delete shows one Undo; the delete runs when the window passes", async () => {
    const clock = fakeClock();
    const onDelete = vi.fn();
    const screen = mount(renderListDelete({ error: false }, { onDelete, undoWindowMs: 5000, clock }));
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    (screen.querySelector(".confirm-yes") as HTMLButtonElement).click();
    await settle();
    expect(screen.querySelectorAll(".undo")).toHaveLength(1);
    expect(screen.querySelector(".undo")?.textContent).toBe(UNDO);
    clock.fire();
    expect(onDelete).toHaveBeenCalledOnce();
    expect(screen.querySelector(".undo")).toBeNull();
  });

  it("Undo cancels the delete and removes the button", async () => {
    const clock = fakeClock();
    const onDelete = vi.fn();
    const screen = mount(renderListDelete({ error: false }, { onDelete, undoWindowMs: 5000, clock }));
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    (screen.querySelector(".confirm-yes") as HTMLButtonElement).click();
    await settle();
    (screen.querySelector(".undo") as HTMLButtonElement).click();
    expect(screen.querySelector(".undo")).toBeNull();
    clock.fire();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("a second delete is not asked while one is pending", async () => {
    const clock = fakeClock();
    const screen = mount(renderListDelete({ error: false }, { onDelete: vi.fn(), undoWindowMs: 5000, clock }));
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    (screen.querySelector(".confirm-yes") as HTMLButtonElement).click();
    await settle();
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    expect(screen.querySelector(".confirm")).toBeNull();
    expect(screen.querySelectorAll(".undo")).toHaveLength(1);
  });

  it("two quick Delete clicks open one confirm and leave one Undo; the delete runs once", async () => {
    const clock = fakeClock();
    const onDelete = vi.fn();
    const screen = mount(renderListDelete({ error: false }, { onDelete, undoWindowMs: 5000, clock }));
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    buttonLabelled(screen, TEXT_LIST_DELETE[2]).click();
    expect(screen.querySelectorAll(".confirm")).toHaveLength(1);
    (screen.querySelector(".confirm-yes") as HTMLButtonElement).click();
    await settle();
    expect(screen.querySelectorAll(".undo")).toHaveLength(1);
    clock.fire();
    expect(onDelete).toHaveBeenCalledOnce();
    expect(screen.querySelector(".undo")).toBeNull();
  });

  it("Cancel button calls onCancel", () => {
    const onCancel = vi.fn();
    const screen = mount(renderListDelete({ error: false }, { onDelete: vi.fn(), onCancel, undoWindowMs: 5000 }));
    buttonLabelled(screen, TEXT_LIST_DELETE[3]).click();
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
