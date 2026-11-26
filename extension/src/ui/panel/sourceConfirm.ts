import { button, el } from "../dom";
import { TEXT_SOURCE_CONFIRM_TREE } from "../strings";

const [TITLE, NOTE, REMOVE, ADD, CANCEL, FAILED] = TEXT_SOURCE_CONFIRM_TREE;

/** Props of the confirm-new-topics screen: the proposed topic labels and whether the read failed. */
export interface SourceConfirmProps {
  topics: string[];
  failed: boolean;
}

/** Actions of the confirm-new-topics screen; each runs only on a click. */
export interface SourceConfirmHandlers {
  onRemove: (index: number) => void;
  onAddToTrack: () => void;
  onCancel: () => void;
}

/**
 * Confirm new topics: one row per proposed topic with a Remove button, then the note that the
 * concepts join the track at once, then Add to track and Cancel. Nothing joins the track until
 * Add to track is clicked. A failed read shows "Could not read this source." instead of the list.
 */
export function renderSourceConfirm(props: SourceConfirmProps, handlers: SourceConfirmHandlers): HTMLElement {
  const screen = el("section", undefined, "source-confirm");
  screen.append(el("h2", TITLE));
  if (props.failed) {
    screen.append(el("p", FAILED, "status error"));
  } else {
    const list = el("ul");
    props.topics.forEach((topic, index) => {
      const item = el("li", undefined, "topic");
      item.append(el("span", topic, "label"), button(REMOVE, () => handlers.onRemove(index), "remove"));
      list.append(item);
    });
    screen.append(list, el("p", NOTE, "note"));
  }
  screen.append(button(ADD, () => handlers.onAddToTrack(), "add-to-track", props.failed || props.topics.length === 0));
  screen.append(button(CANCEL, () => handlers.onCancel(), "cancel"));
  return screen;
}
