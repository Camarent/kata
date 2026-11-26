import type { PanelHandlers } from "../../sidepanel";
import { CoreOfflineError } from "../../coreClient";
import { el } from "../dom";
import { TEXT_COURSE_GENERATE } from "../strings";

const [
  HEADING,
  NEW_NOTE,
  KNOWN_NOTE,
  START_NOTE,
  ADD_EXAM,
  EXAM_NOTE,
  SUBMIT,
  CANCEL,
  GENERATING,
  FAILED,
  SERVER_DOWN,
  NO_TITLE,
] = TEXT_COURSE_GENERATE;

/** Props of the generate screen: whether the core is down and how to leave the screen. */
export interface CourseGenerateProps {
  serverDown: boolean;
  onCancel: () => void;
  /** Called after the course is queued; the caller leaves the screen. */
  onDone: () => void;
}

/**
 * Generate-course form: a title, the notes on which concepts go in, and Generate. An empty title is
 * refused before the request ("Give the course a title."). While onCreateCourse runs the button shows
 * "Generating..." and is disabled; on success onDone runs. A rejected request shows "Server down.
 * Generate course is off." when the core is offline, else the could-not-generate text.
 */
export function renderCourseGenerate(handlers: PanelHandlers, props: CourseGenerateProps): HTMLElement {
  const form = el("form", undefined, "course-generate");
  form.append(el("h2", HEADING));
  form.append(el("p", NEW_NOTE), el("p", KNOWN_NOTE), el("p", START_NOTE));
  // The exam option is shown but disabled: the create request has no exam field yet (task-14 rework item 3).
  const examLabel = el("label", ADD_EXAM);
  const exam = el("input");
  exam.type = "checkbox";
  exam.disabled = true;
  examLabel.prepend(exam);
  form.append(examLabel, el("p", EXAM_NOTE));
  const title = el("input");
  title.name = "title";
  title.type = "text";
  title.setAttribute("aria-label", HEADING);
  const submit = el("button", SUBMIT);
  submit.type = "submit";
  submit.disabled = props.serverDown;
  const cancel = el("button", CANCEL);
  cancel.type = "button";
  cancel.addEventListener("click", () => props.onCancel());
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  form.append(title, submit, cancel);
  if (props.serverDown) form.append(el("p", SERVER_DOWN, "notice"));
  form.append(error);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const value = title.value.trim();
    if (value === "") {
      error.textContent = NO_TITLE;
      return;
    }
    submit.disabled = true;
    submit.textContent = GENERATING;
    try {
      await handlers.onCreateCourse(value);
    } catch (err) {
      error.textContent = err instanceof CoreOfflineError ? SERVER_DOWN : FAILED;
      submit.disabled = props.serverDown;
      submit.textContent = SUBMIT;
      return;
    }
    props.onDone();
  });
  return form;
}
