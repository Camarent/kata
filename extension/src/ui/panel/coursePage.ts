import { el } from "../dom";
import { TEXT_COURSE_PAGE } from "../strings";

const [ITEMS, START_EXAM, BACK, LOAD_FAILED] = TEXT_COURSE_PAGE;

/** Props of the course page: the course title, its items and the Back exit. */
export interface CoursePageProps {
  title: string;
  items: string[];
  loadFailed: boolean;
  onBack: () => void;
}

/**
 * Course page: the course title, the list of course items and Back to panel. A failed load shows the
 * could-not-load text in place of the items.
 */
export function renderCoursePage(props: CoursePageProps): HTMLElement {
  const page = el("main", undefined, "course-page");
  page.append(el("h1", props.title));
  if (props.loadFailed) {
    page.append(el("p", LOAD_FAILED, "error"));
  } else {
    page.append(el("h2", ITEMS));
    const list = el("ul", undefined, "course-items");
    for (const item of props.items) list.append(el("li", item));
    page.append(list);
  }
  // Start exam has no core route yet (task-14 rework item 3): shown disabled.
  const startExam = el("button", START_EXAM);
  startExam.type = "button";
  startExam.disabled = true;
  const back = el("button", BACK);
  back.type = "button";
  back.addEventListener("click", () => props.onBack());
  page.append(startExam, back);
  return page;
}
