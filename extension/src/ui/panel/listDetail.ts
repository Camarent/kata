import { button, el } from "../dom";
import { TEXT_LIST_DETAIL } from "../strings";

const [TITLE, DRAFT_NOTE, RENAME, DELETE, REMOVE, ADD_TOPIC, GENERATE, BACK, EMPTY, ERROR] = TEXT_LIST_DETAIL;

/** Data state of the list: ready shows the concepts; empty and error show one status line. */
export type ListDetailState = "ready" | "empty" | "error";

/** Props of the list-detail screen: the list name, its state and its concept labels in order. */
export interface ListDetailProps {
  name: string;
  state: ListDetailState;
  concepts: string[];
}

/** User actions on the list. Each button appears only when its handler is present. */
export interface ListDetailActions {
  onRename?: () => void;
  onDelete?: () => void;
  onRemove?: (index: number) => void;
  onAddTopic?: () => void;
  onGenerate?: () => void;
  onBack?: () => void;
}

/**
 * List detail: the name, the draft note, the concepts with Remove, and the actions. Empty and
 * error states show their status line in place of the concepts. Generate course is off unless
 * the list is ready.
 */
export function renderListDetail(props: ListDetailProps, actions: ListDetailActions): HTMLElement {
  const screen = el("section", undefined, "list-detail");
  screen.append(el("h2", TITLE), el("h3", props.name, "list-name"), el("p", DRAFT_NOTE, "note"));

  if (props.state === "error") {
    screen.append(el("p", ERROR, "status"));
  } else if (props.state === "empty") {
    screen.append(el("p", EMPTY, "empty"));
  } else {
    const list = el("ul", undefined, "concepts");
    props.concepts.forEach((label, index) => {
      const item = el("li", undefined, "concept");
      item.append(el("span", label, "label"));
      if (actions.onRemove) {
        const handler = actions.onRemove;
        item.append(button(REMOVE, () => handler(index), "remove"));
      }
      list.append(item);
    });
    screen.append(list);
  }

  if (actions.onRename) screen.append(button(RENAME, () => actions.onRename?.(), "rename"));
  if (actions.onAddTopic) screen.append(button(ADD_TOPIC, () => actions.onAddTopic?.(), "add-topic"));
  if (actions.onGenerate) {
    screen.append(button(GENERATE, () => actions.onGenerate?.(), "generate", props.state !== "ready"));
  }
  if (actions.onDelete) screen.append(button(DELETE, () => actions.onDelete?.(), "delete"));
  if (actions.onBack) screen.append(button(BACK, () => actions.onBack?.(), "back"));
  return screen;
}
