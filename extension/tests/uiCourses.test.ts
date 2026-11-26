import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoreOfflineError, type CourseSummary } from "../src/coreClient";
import type { PanelHandlers } from "../src/sidepanel";
import { renderCourseDetail, renderCourseRegenerate } from "../src/ui/panel/courseDetail";
import { renderCourseGenerate } from "../src/ui/panel/courseGenerate";
import { renderCoursePage } from "../src/ui/panel/coursePage";
import { renderCoursesTab } from "../src/ui/panel/coursesTab";
import { TEXT_COURSE_DETAIL, TEXT_COURSE_GENERATE, TEXT_COURSE_PAGE, TEXT_COURSE_REGENERATE, TEXT_COURSES_TAB } from "../src/ui/strings";

const course: CourseSummary = {
  id: 7,
  title: "Linear algebra",
  status: "ready",
  concept_ids: [1, 2],
  error: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-02T10:00:00Z",
};

function handlers(overrides: Partial<PanelHandlers> = {}): PanelHandlers {
  return {
    onSignIn: vi.fn(),
    onDisconnect: vi.fn(),
    onChangeServer: vi.fn(),
    onCancelChange: vi.fn(),
    onKnown: vi.fn(async () => "saved" as const),
    onScan: vi.fn(async () => {}),
    onReview: vi.fn(async () => {}),
    onSetConcept: vi.fn(async () => {}),
    onCloseReview: vi.fn(),
    onOpenCourse: vi.fn(async () => {}),
    onDeleteCourse: vi.fn(async () => {}),
    onCreateCourse: vi.fn(async () => {}),
    onRegenerateCourse: vi.fn(async () => {}),
    onModelhost: vi.fn(async () => ({ ok: true, text: "done" })),
    ...overrides,
  };
}

/** Button with the given visible text inside root; fails the test when there is none. */
function buttonNamed(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text);
  if (found === undefined) throw new Error(`no button "${text}"`);
  return found;
}

/** Text of every element of root matching the selector, in document order. */
function textsOf(root: HTMLElement, selector: string): (string | null)[] {
  return [...root.querySelectorAll(selector)].map((node) => node.textContent);
}

/** Types the title into the generate form's title input; fails the test when there is none. */
function fillTitle(root: HTMLElement, value: string): void {
  const input = root.querySelector<HTMLInputElement>("input[name=title]");
  if (input === null) throw new Error("no title input");
  input.value = value;
}

/** Lets pending promise handlers settle. */
async function flush(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("courses tab, one test per inventory state", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("lists each ready course with Open course", () => {
    const h = handlers();
    root.append(renderCoursesTab(h, { courses: [course], loadFailed: false, serverDown: false, onGenerate: vi.fn() }));
    expect(textsOf(root, "h2")).toEqual([TEXT_COURSES_TAB[0]]);
    expect(textsOf(root, "li span")).toEqual(["Linear algebra"]);
    buttonNamed(root, TEXT_COURSES_TAB[5]).click();
    expect(h.onOpenCourse).toHaveBeenCalledWith(7);
  });

  it("shows the empty text when there are no courses", () => {
    root.append(renderCoursesTab(handlers(), { courses: [], loadFailed: false, serverDown: false, onGenerate: vi.fn() }));
    expect(textsOf(root, "p.empty")).toEqual([TEXT_COURSES_TAB[3]]);
  });

  it("deletes a course after confirm and calls onDeleteCourse", async () => {
    const h = handlers();
    root.append(renderCoursesTab(h, { courses: [course], loadFailed: false, serverDown: false, onGenerate: vi.fn() }));
    buttonNamed(root, TEXT_COURSES_TAB[25]).click();
    const yes = root.querySelector<HTMLButtonElement>(".confirm-yes");
    if (yes === null) throw new Error("no confirm box");
    yes.click();
    await flush();
    expect(h.onDeleteCourse).toHaveBeenCalledWith(7);
  });

  it("keeps the course when the delete is cancelled", async () => {
    const h = handlers();
    root.append(renderCoursesTab(h, { courses: [course], loadFailed: false, serverDown: false, onGenerate: vi.fn() }));
    buttonNamed(root, TEXT_COURSES_TAB[25]).click();
    const no = root.querySelector<HTMLButtonElement>(".confirm-no");
    if (no === null) throw new Error("no confirm box");
    no.click();
    await flush();
    expect(h.onDeleteCourse).not.toHaveBeenCalled();
    expect(root.querySelector(".confirm")).toBeNull();
  });

  it("shows the could-not-delete text when the delete fails", async () => {
    const h = handlers({ onDeleteCourse: vi.fn(async () => { throw new Error("boom"); }) });
    root.append(renderCoursesTab(h, { courses: [course], loadFailed: false, serverDown: false, onGenerate: vi.fn() }));
    buttonNamed(root, TEXT_COURSES_TAB[25]).click();
    root.querySelector<HTMLButtonElement>(".confirm-yes")?.click();
    await flush();
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSES_TAB[28]]);
  });

  it("shows the could-not-load text in place of the list", () => {
    root.append(renderCoursesTab(handlers(), { courses: [course], loadFailed: true, serverDown: false, onGenerate: vi.fn() }));
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSES_TAB[23]]);
    expect(root.querySelector("ul")).toBeNull();
  });

  it("turns Generate course off and shows the server-down text when the core is down", () => {
    root.append(renderCoursesTab(handlers(), { courses: [], loadFailed: false, serverDown: true, onGenerate: vi.fn() }));
    expect(buttonNamed(root, TEXT_COURSES_TAB[8]).disabled).toBe(true);
    expect(textsOf(root, "p.notice")).toEqual([TEXT_COURSES_TAB[24]]);
  });

  it("opens the generate screen from Generate course", () => {
    const onGenerate = vi.fn();
    root.append(renderCoursesTab(handlers(), { courses: [], loadFailed: false, serverDown: false, onGenerate }));
    buttonNamed(root, TEXT_COURSES_TAB[8]).click();
    expect(onGenerate).toHaveBeenCalledTimes(1);
  });
});

describe("course generate, one test per inventory state", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("shows the heading, the notes and the buttons", () => {
    root.append(renderCourseGenerate(handlers(), { serverDown: false, onCancel: vi.fn(), onDone: vi.fn() }));
    expect(textsOf(root, "h2")).toEqual([TEXT_COURSE_GENERATE[0]]);
    expect(textsOf(root, "p:not(.error)")).toEqual([
      TEXT_COURSE_GENERATE[1],
      TEXT_COURSE_GENERATE[2],
      TEXT_COURSE_GENERATE[3],
      TEXT_COURSE_GENERATE[5],
    ]);
    expect(root.querySelector("label")?.textContent).toBe(TEXT_COURSE_GENERATE[4]);
    expect(root.querySelector<HTMLInputElement>("label input")?.disabled).toBe(true);
    expect(buttonNamed(root, TEXT_COURSE_GENERATE[6]).disabled).toBe(false);
  });

  it("sends the typed title to onCreateCourse on submit", async () => {
    const h = handlers();
    root.append(renderCourseGenerate(h, { serverDown: false, onCancel: vi.fn(), onDone: vi.fn() }));
    const input = root.querySelector<HTMLInputElement>("input[name=title]");
    if (input === null) throw new Error("no title input");
    input.value = "  Algebra  ";
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(h.onCreateCourse).toHaveBeenCalledWith("Algebra");
  });

  it("shows Generating... and disables the button while the request runs", () => {
    const h = handlers({ onCreateCourse: vi.fn(() => new Promise<void>(() => {})) });
    root.append(renderCourseGenerate(h, { serverDown: false, onCancel: vi.fn(), onDone: vi.fn() }));
    fillTitle(root, "Algebra");
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    const submit = root.querySelector<HTMLButtonElement>("button[type=submit]");
    expect(submit?.textContent).toBe(TEXT_COURSE_GENERATE[8]);
    expect(submit?.disabled).toBe(true);
  });

  it("shows the could-not-generate text when the request fails", async () => {
    const h = handlers({ onCreateCourse: vi.fn(async () => { throw new Error("boom"); }) });
    root.append(renderCourseGenerate(h, { serverDown: false, onCancel: vi.fn(), onDone: vi.fn() }));
    fillTitle(root, "Algebra");
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_GENERATE[9]]);
  });

  it("shows the server-down text when the core is offline", async () => {
    const h = handlers({ onCreateCourse: vi.fn(async () => { throw new CoreOfflineError(); }) });
    root.append(renderCourseGenerate(h, { serverDown: false, onCancel: vi.fn(), onDone: vi.fn() }));
    fillTitle(root, "Algebra");
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_GENERATE[10]]);
  });

  it("refuses an empty title before the request and shows the give-a-title text", async () => {
    const h = handlers();
    root.append(renderCourseGenerate(h, { serverDown: false, onCancel: vi.fn(), onDone: vi.fn() }));
    const input = root.querySelector<HTMLInputElement>("input[name=title]");
    if (input === null) throw new Error("no title input");
    input.value = "   ";
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(h.onCreateCourse).not.toHaveBeenCalled();
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_GENERATE[11]]);
  });

  it("calls onDone once the course is queued", async () => {
    const onDone = vi.fn();
    const h = handlers();
    root.append(renderCourseGenerate(h, { serverDown: false, onCancel: vi.fn(), onDone }));
    const input = root.querySelector<HTMLInputElement>("input[name=title]");
    if (input === null) throw new Error("no title input");
    input.value = "Algebra";
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("disables Generate when the core is down", () => {
    root.append(renderCourseGenerate(handlers(), { serverDown: true, onCancel: vi.fn(), onDone: vi.fn() }));
    expect(buttonNamed(root, TEXT_COURSE_GENERATE[6]).disabled).toBe(true);
  });
});

describe("course preview and regenerate, one test per inventory state", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("preview shows the title, the start note and the exits", () => {
    const h = handlers();
    const onRegenerate = vi.fn();
    const onBack = vi.fn();
    root.append(renderCourseDetail(h, { course, loadFailed: false, onBack, onRegenerate }));
    expect(textsOf(root, "h2")).toEqual([TEXT_COURSE_DETAIL[0]]);
    expect(textsOf(root, "h3")).toEqual(["Linear algebra"]);
    buttonNamed(root, TEXT_COURSE_DETAIL[3]).click();
    expect(h.onOpenCourse).toHaveBeenCalledWith(7);
    buttonNamed(root, TEXT_COURSE_DETAIL[4]).click();
    expect(onRegenerate).toHaveBeenCalledTimes(1);
    buttonNamed(root, TEXT_COURSE_DETAIL[6]).click();
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(buttonNamed(root, TEXT_COURSE_DETAIL[2]).disabled).toBe(true);
    expect(buttonNamed(root, TEXT_COURSE_DETAIL[5]).disabled).toBe(true);
  });

  it("preview shows the could-not-load text and disables the course actions when the load fails", () => {
    root.append(renderCourseDetail(handlers(), { course, loadFailed: true, onBack: vi.fn(), onRegenerate: vi.fn() }));
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_DETAIL[8]]);
    expect(buttonNamed(root, TEXT_COURSE_DETAIL[3]).disabled).toBe(true);
    expect(buttonNamed(root, TEXT_COURSE_DETAIL[4]).disabled).toBe(true);
  });

  it("regenerate shows the warning, the carried and new notes", () => {
    root.append(renderCourseRegenerate(handlers(), { course, onCancel: vi.fn(), onDone: vi.fn() }));
    expect(textsOf(root, "h2")).toEqual([TEXT_COURSE_REGENERATE[0]]);
    expect(textsOf(root, "p:not(.error)")).toEqual([
      TEXT_COURSE_REGENERATE[1],
      TEXT_COURSE_REGENERATE[3],
      TEXT_COURSE_REGENERATE[5],
      TEXT_COURSE_REGENERATE[6],
    ]);
  });

  it("regenerate calls onRegenerateCourse with the course id, not onCreateCourse", async () => {
    const h = handlers();
    root.append(renderCourseRegenerate(h, { course, onCancel: vi.fn(), onDone: vi.fn() }));
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(h.onRegenerateCourse).toHaveBeenCalledWith(course.id);
    expect(h.onCreateCourse).not.toHaveBeenCalled();
  });

  it("regenerate shows the could-not-regenerate text when the request fails", async () => {
    const h = handlers({ onRegenerateCourse: vi.fn(async () => { throw new Error("boom"); }) });
    root.append(renderCourseRegenerate(h, { course, onCancel: vi.fn(), onDone: vi.fn() }));
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_REGENERATE[9]]);
  });

  it("regenerate shows the server-down text when the core is offline", async () => {
    const h = handlers({ onRegenerateCourse: vi.fn(async () => { throw new CoreOfflineError(); }) });
    root.append(renderCourseRegenerate(h, { course, onCancel: vi.fn(), onDone: vi.fn() }));
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_GENERATE[10]]);
  });

  it("regenerate disables Regenerate while the request runs", () => {
    const h = handlers({ onRegenerateCourse: vi.fn(() => new Promise<void>(() => {})) });
    root.append(renderCourseRegenerate(h, { course, onCancel: vi.fn(), onDone: vi.fn() }));
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    const submit = root.querySelector<HTMLButtonElement>("button[type=submit]");
    expect(submit?.disabled).toBe(true);
  });

  it("regenerate calls onDone once the request is accepted", async () => {
    const onDone = vi.fn();
    root.append(renderCourseRegenerate(handlers(), { course, onCancel: vi.fn(), onDone }));
    root.querySelector("form")?.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("regenerate Cancel calls onCancel", () => {
    const onCancel = vi.fn();
    root.append(renderCourseRegenerate(handlers(), { course, onCancel, onDone: vi.fn() }));
    buttonNamed(root, TEXT_COURSE_REGENERATE[8]).click();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("course page, one test per inventory state", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("lists the course items and calls onBack from Back to panel", () => {
    const onBack = vi.fn();
    root.append(renderCoursePage({ title: "Linear algebra", items: ["Vectors", "Matrices"], loadFailed: false, onBack }));
    expect(textsOf(root, "h2")).toEqual([TEXT_COURSE_PAGE[0]]);
    expect(textsOf(root, "li")).toEqual(["Vectors", "Matrices"]);
    buttonNamed(root, TEXT_COURSE_PAGE[2]).click();
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(buttonNamed(root, TEXT_COURSE_PAGE[1]).disabled).toBe(true);
  });

  it("shows the could-not-load text in place of the items", () => {
    root.append(renderCoursePage({ title: "Linear algebra", items: [], loadFailed: true, onBack: vi.fn() }));
    expect(textsOf(root, "p.error")).toEqual([TEXT_COURSE_PAGE[3]]);
    expect(root.querySelector("ul")).toBeNull();
  });
});
