import type { PanelHandlers } from "../../types";
import type { CourseSummary } from "../../coreClient";
import { askConfirm } from "../confirm";
import { el } from "../dom";
import { TEXT_COURSES_TAB } from "../strings";

const COURSES = TEXT_COURSES_TAB[0];
const NO_COURSES = TEXT_COURSES_TAB[3];
const OPEN_COURSE = TEXT_COURSES_TAB[5];
const GENERATE = TEXT_COURSES_TAB[8];
const LOAD_FAILED = TEXT_COURSES_TAB[23];
const SERVER_DOWN = TEXT_COURSES_TAB[24];
const DELETE = TEXT_COURSES_TAB[25];
const DELETE_ASK = TEXT_COURSES_TAB[26];
const DELETE_YES = TEXT_COURSES_TAB[27];
const DELETE_FAILED = TEXT_COURSES_TAB[28];

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

/** Props of the courses tab: the ready courses and the state of the core connection. */
export interface CoursesTabProps {
  courses: CourseSummary[];
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
    open.addEventListener("click", () => void handlers.onOpenCourse(course.id));
    const remove = el("button", DELETE);
    remove.type = "button";
    remove.addEventListener("click", () => void confirmDelete(handlers, item, course.id, error));
    item.append(open, remove);
    list.append(item);
  }
  tab.append(list, error);
  return tab;
}
