import { button, el } from "../dom";
import { TEXT_LIST_EDIT } from "../strings";

const [LABEL, SAVE, CANCEL, SAVE_ERROR, DUPLICATE_ERROR] = TEXT_LIST_EDIT;

/** Error shown under the name field: null for none, else the failed reason. */
export type ListEditError = null | "save" | "duplicate";

/** Props of the name-a-list screen: the current name and the error from the last try, if any. */
export interface ListEditProps {
  name: string;
  error: ListEditError;
}

/** Save gets the typed name, trimmed; Cancel leaves the name as it was. */
export interface ListEditActions {
  onSave: (name: string) => void;
  onCancel: () => void;
}

const ERROR_TEXT: Record<Exclude<ListEditError, null>, string> = {
  save: SAVE_ERROR,
  duplicate: DUPLICATE_ERROR,
};

/** Name a list: one text field with its label, the error line when there is one, Save and Cancel. */
export function renderListEdit(props: ListEditProps, actions: ListEditActions): HTMLElement {
  const screen = el("section", undefined, "list-edit");
  const field = el("label", undefined, "name-field");
  const input = el("input", undefined, "name-input");
  input.type = "text";
  input.value = props.name;
  field.append(el("span", LABEL, "label"), input);
  screen.append(field);

  if (props.error !== null) screen.append(el("p", ERROR_TEXT[props.error], "error"));

  screen.append(
    button(SAVE, () => actions.onSave(input.value.trim()), "save"),
    button(CANCEL, () => actions.onCancel(), "cancel"),
  );
  return screen;
}
