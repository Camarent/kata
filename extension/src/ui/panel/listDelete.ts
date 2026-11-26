import { askConfirm } from "../confirm";
import { button, el } from "../dom";
import { TEXT_LIST_DELETE, TEXT_PIN } from "../strings";
import { type Clock, deferCommit, type DeferredCommit } from "../undo";

const [QUESTION, NOTE, DELETE, CANCEL, ERROR] = TEXT_LIST_DELETE;
const UNDO = TEXT_PIN[6];

/** Props of the delete-list screen: whether the last delete failed. */
export interface ListDeleteProps {
  error: boolean;
}

/** Delete runs once the undo window passes; Cancel leaves the list as it is. */
export interface ListDeleteActions {
  onDelete: () => void;
  onCancel?: () => void;
  /** Undo window in milliseconds before the delete is committed. */
  undoWindowMs: number;
  /** Timer source; tests inject a fake one. Defaults to the window clock. */
  clock?: Clock;
}

/**
 * Delete list: a Delete button asks for confirmation inline, then offers one Undo for the
 * undo window before onDelete runs. Only one delete is pending at a time.
 */
export function renderListDelete(props: ListDeleteProps, actions: ListDeleteActions): HTMLElement {
  const screen = el("section", undefined, "list-delete");
  screen.append(el("p", NOTE, "note"));
  if (props.error) screen.append(el("p", ERROR, "error"));

  let pending: DeferredCommit | null = null;
  // True while a confirm box is open: a second Delete click must not open another one.
  let confirming = false;
  const undoSlot = el("div", undefined, "undo-slot");

  const request = async (): Promise<void> => {
    if (confirming || pending?.pending) return;
    confirming = true;
    let ok: boolean;
    try {
      ok = await askConfirm(screen, { message: QUESTION, confirmLabel: DELETE, cancelLabel: CANCEL });
    } finally {
      confirming = false;
    }
    if (!ok) return;
    const undoButton = button(UNDO, () => {
      if (commit.undo()) undoButton.remove();
    }, "undo");
    const commit = deferCommit(
      () => {
        undoButton.remove();
        actions.onDelete();
      },
      actions.undoWindowMs,
      actions.clock,
    );
    pending = commit;
    undoSlot.append(undoButton);
  };

  screen.append(button(DELETE, () => void request(), "delete"), undoSlot);
  if (actions.onCancel) {
    const handler = actions.onCancel;
    screen.append(button(CANCEL, () => handler(), "cancel"));
  }
  return screen;
}
