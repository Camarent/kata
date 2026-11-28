import type { PanelState } from "./sidepanel";

/** Closes the course page: back to the Courses list. The caller passes the panel state and its redraw. */
export function closeCourse(state: PanelState, draw: () => void): void {
  state.coursePage = null;
  draw();
}
