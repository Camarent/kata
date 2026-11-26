import type { PanelHandlers } from "../../types";
import type { CourseSummary } from "../../coreClient";
import { askConfirm } from "../confirm";
import { el } from "../dom";
import { COURSES_TAB_TEXT } from "../strings";

const COURSES = COURSES_TAB_TEXT.courses;
const NO_COURSES = COURSES_TAB_TEXT.noCourses;
const OPEN_COURSE = COURSES_TAB_TEXT.openCourse;
const GENERATE = COURSES_TAB_TEXT.generate;
const LOAD_FAILED = COURSES_TAB_TEXT.loadFailed;
const SERVER_DOWN = COURSES_TAB_TEXT.serverDown;
const DELETE = COURSES_TAB_TEXT.deleteCourse;
const DELETE_ASK = COURSES_TAB_TEXT.deleteAsk;
const DELETE_YES = COURSES_TAB_TEXT.deleteYes;
const DELETE_FAILED = COURSES_TAB_TEXT.deleteFailed;

/** Asks before deleting: the confirm box opens inside the row; a failed delete shows the error line. */
async function confirmDelete(
  handlers: PanelHandlers,
  row: HTMLElement,
  courseId: number,
  error: HTMLElement,
): Promise<void> {
  error.textContent = "";
  const ok = await askConfirm(row, { message: DELETE_ASK, confirmLabel: DELETE_YES });
  if (!ok) return;
  try {
    await handlers.onDeleteCourse(courseId);
  } catch {
    error.textContent = DELETE_FAILED;
  }
}

/** Opens a course; a refused open shows its error text on the error line and turns the button on again. */
async function openCourse(
  handlers: PanelHandlers,
  button: HTMLButtonElement,
  courseId: number,
  error: HTMLElement,
): Promise<void> {
  error.textContent = "";
  button.disabled = true;
  try {
    await handlers.onOpenCourse(courseId);
  } catch (err) {
    error.textContent = err instanceof Error ? err.message : String(err);
  } finally {
    button.disabled = false;
  }
}

/** Props of the courses tab: the ready courses and the state of the core connection. */
export interface CoursesTabProps {
  courses: Pick<CourseSummary, "id" | "title">[];
  /** Course limit of the server; the tab shows "n of limit" when it is above 0. */
  courseLimit?: number;
  /** Courses counted against the limit; defaults to the number of listed courses. */
  courseTotal?: number;
  /** True when the courses could not be loaded; shows the could-not-load text instead of the list. */
  loadFailed: boolean;
  /** True when the core is down; Generate course is then off. */
  serverDown: boolean;
  /** Opens the generate screen. */
  onGenerate: () => void;
}

/**
 * Courses tab: the ready courses, each with Open course (handlers.onOpenCourse) and Delete (confirmed,
 * then handlers.onDeleteCourse), and Generate course.
 * With no courses the tab shows the empty text; with a failed load it shows the could-not-load text.
 */
export function renderCoursesTab(handlers: PanelHandlers, props: CoursesTabProps): HTMLElement {
  const tab = el("section", undefined, "courses-tab");
  tab.append(el("h2", COURSES));
  const generate = el("button", GENERATE);
  generate.type = "button";
  generate.disabled = props.serverDown;
  generate.addEventListener("click", () => props.onGenerate());
  tab.append(generate);
  if ((props.courseLimit ?? 0) > 0) {
    const total = props.courseTotal ?? props.courses.length;
    tab.append(el("p", `${total} of ${props.courseLimit}`, "course-limit"));
  }
  if (props.serverDown) tab.append(el("p", SERVER_DOWN, "notice"));
  if (props.loadFailed) {
    tab.append(el("p", LOAD_FAILED, "error"));
    return tab;
  }
  if (props.courses.length === 0) {
    tab.append(el("p", NO_COURSES, "empty"));
    return tab;
  }
  const list = el("ul", undefined, "course-list");
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  for (const course of props.courses) {
    const item = el("li");
    item.append(el("span", course.title));
    const open = el("button", OPEN_COURSE);
    open.type = "button";
    open.addEventListener("click", () => void openCourse(handlers, open, course.id, error));
    const remove = el("button", DELETE);
    remove.type = "button";
    remove.addEventListener("click", () => void confirmDelete(handlers, item, course.id, error));
    item.append(open, remove);
    list.append(item);
  }
  tab.append(list, error);
  return tab;
}
