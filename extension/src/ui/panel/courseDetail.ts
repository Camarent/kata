import type { PanelHandlers } from "../../types";
import type { CourseSummary } from "../../coreClient";
import { CoreOfflineError } from "../../coreClient";
import { el } from "../dom";
import { TEXT_COURSE_DETAIL, TEXT_COURSE_GENERATE, TEXT_COURSE_REGENERATE } from "../strings";

const [PREVIEW, START_NOTE, CHANGE_START, OPEN_PAGE, REGENERATE, START_EXAM, BACK, , LOAD_FAILED] =
  TEXT_COURSE_DETAIL;
const [
  REGEN_HEADING,
  REGEN_WARNING,
  CARRIED,
  CARRIED_NOTE,
  NEW,
  NEW_NOTE,
  REGEN_START,
  REGEN_SUBMIT,
  REGEN_CANCEL,
  REGEN_FAILED,
] = TEXT_COURSE_REGENERATE;
const SERVER_DOWN_LABEL = TEXT_COURSE_GENERATE[10];

/** Props of the course preview: the course and the two screen exits. */
export interface CourseDetailProps {
  course: CourseSummary;
  loadFailed: boolean;
  onBack: () => void;
  onRegenerate: () => void;
}

/**
 * Course preview: title, the learning-start note, Open course page (handlers.onOpenCourse),
 * Regenerate and Back. A failed load shows the could-not-load text in place of the details.
 */
export function renderCourseDetail(handlers: PanelHandlers, props: CourseDetailProps): HTMLElement {
  const screen = el("section", undefined, "course-detail");
  screen.append(el("h2", PREVIEW));
  if (props.loadFailed) {
    screen.append(el("p", LOAD_FAILED, "error"));
  } else {
    screen.append(el("h3", props.course.title), el("p", START_NOTE));
  }
  const openPage = el("button", OPEN_PAGE);
  openPage.type = "button";
  openPage.disabled = props.loadFailed;
  openPage.addEventListener("click", () => void handlers.onOpenCourse(props.course.id));
  const regenerate = el("button", REGENERATE);
  regenerate.type = "button";
  regenerate.disabled = props.loadFailed;
  regenerate.addEventListener("click", () => props.onRegenerate());
  // Start and exam have no core route yet (task-14 rework item 3): shown disabled.
  const changeStart = el("button", CHANGE_START);
  changeStart.type = "button";
  changeStart.disabled = true;
  const startExam = el("button", START_EXAM);
  startExam.type = "button";
  startExam.disabled = true;
  const back = el("button", BACK);
  back.type = "button";
  back.addEventListener("click", () => props.onBack());
  screen.append(openPage, changeStart, startExam, regenerate, back);
  return screen;
}

/** Props of the regenerate screen: the course to rebuild, the Cancel exit and the success exit. */
export interface CourseRegenerateProps {
  course: CourseSummary;
  onCancel: () => void;
  /** Called after the request is accepted; the caller leaves the screen. */
  onDone: () => void;
}

/**
 * Regenerate form: states that the new course is version 2, that concept states are kept and that
 * new sources add concepts. Regenerate asks the core to rebuild this course
 * (handlers.onRegenerateCourse, never onCreateCourse: the same title returns 409). A rejected request shows "Server down. Generate course is off." when the
 * core is offline, else the could-not-regenerate text.
 */
export function renderCourseRegenerate(handlers: PanelHandlers, props: CourseRegenerateProps): HTMLElement {
  const form = el("form", undefined, "course-regenerate");
  form.append(el("h2", REGEN_HEADING), el("p", REGEN_WARNING));
  form.append(el("h3", CARRIED), el("p", CARRIED_NOTE));
  form.append(el("h3", NEW), el("p", NEW_NOTE));
  form.append(el("p", REGEN_START));
  const submit = el("button", REGEN_SUBMIT);
  submit.type = "submit";
  const cancel = el("button", REGEN_CANCEL);
  cancel.type = "button";
  cancel.addEventListener("click", () => props.onCancel());
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  form.append(submit, cancel, error);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    submit.disabled = true;
    try {
      await handlers.onRegenerateCourse(props.course.id);
    } catch (err) {
      error.textContent = err instanceof CoreOfflineError ? SERVER_DOWN_LABEL : REGEN_FAILED;
      submit.disabled = false;
      return;
    }
    props.onDone();
  });
  return form;
}
