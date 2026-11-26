import { button, el } from "../dom";
import { TEXT_SOURCE_ADD } from "../strings";

const [TITLE, PASTE, CHOOSE_FILE, USE_PAGE, USE_COURSE, SUBMIT, CANCEL, READING, FAILED, NOT_TEACHING] = TEXT_SOURCE_ADD;

/** Where the add-source screen stands: idle, reading the chosen source, or a read that failed or found no teaching content. */
export type SourceAddStatus = "idle" | "reading" | "failed" | "not-teaching";

/** Props of the add-source screen. */
export interface SourceAddProps {
  status: SourceAddStatus;
}

/** Actions of the add-source screen; each runs only on a click. */
export interface SourceAddHandlers {
  onPasteText: () => void;
  onChooseFile: () => void;
  onUsePage: () => void;
  onUseCourse: () => void;
  onAddSource: () => void;
  onCancel: () => void;
}

/**
 * Add-source screen: the four ways to give a source (Paste text, Choose file, Use current page,
 * Use a course), the Add source submit and Cancel. While a read runs the screen shows "Reading the
 * source..." and the submit is disabled. A failed read shows "Could not read this source.", and a
 * source with no teaching content shows "Nothing here looks like teaching content.".
 */
export function renderSourceAdd(props: SourceAddProps, handlers: SourceAddHandlers): HTMLElement {
  const screen = el("section", undefined, "source-add");
  screen.append(el("h2", TITLE));
  const reading = props.status === "reading";
  screen.append(
    button(PASTE, () => handlers.onPasteText(), "paste-text", reading),
    button(CHOOSE_FILE, () => handlers.onChooseFile(), "choose-file", reading),
    button(USE_PAGE, () => handlers.onUsePage(), "use-page", reading),
    button(USE_COURSE, () => handlers.onUseCourse(), "use-course", reading),
  );
  if (reading) screen.append(el("p", READING, "status"));
  if (props.status === "failed") screen.append(el("p", FAILED, "status error"));
  if (props.status === "not-teaching") screen.append(el("p", NOT_TEACHING, "status"));
  screen.append(button(SUBMIT, () => handlers.onAddSource(), "add-source", reading));
  screen.append(button(CANCEL, () => handlers.onCancel(), "cancel"));
  return screen;
}
