import type { CoreClient } from "../../coreClient";
import { button, el } from "../dom";
import { IGNORED_LIST_TEXT, PIN_TEXT } from "../strings";

const {
  title: TITLE,
  note: NOTE,
  empty: EMPTY,
  restore: RESTORE,
  back: BACK,
  topic: TOPIC,
  word: WORD,
  restored: RESTORED,
} = IGNORED_LIST_TEXT;
// The shared "Undo" is read by key from PIN_TEXT, not by index.
const TEXT_UNDO = PIN_TEXT.undo;

/** The two ignored calls of the core client that Restore and Undo use. */
export type IgnoredClient = Pick<CoreClient, "ignoreConcept" | "unignoreConcept">;

/**
 * Handlers that reach the core: Restore calls `unignoreConcept`, Undo calls `ignoreConcept` again.
 * A failed core call rejects (the list keeps the row); `onChanged` runs after a successful call so the
 * caller can redraw the list. A failing `onChanged` is logged, not rethrown: the core call already succeeded.
 */
export function ignoredClientHandlers(
  client: IgnoredClient,
  onChanged: (action: "restore" | "undo", conceptId: number) => void | Promise<void>,
  onBack?: () => void,
): IgnoredListHandlers {
  const notify = async (action: "restore" | "undo", conceptId: number) => {
    try {
      await onChanged(action, conceptId);
    } catch (err: unknown) {
      console.error(err);
    }
  };
  return {
    onRestore: async (conceptId) => {
      await client.unignoreConcept(conceptId);
      await notify("restore", conceptId);
    },
    onUndo: async (conceptId) => {
      await client.ignoreConcept(conceptId);
      await notify("undo", conceptId);
    },
    onBack,
  };
}

/** One ignored concept on the list: its id, its label and its kind when the core tells it. */
export interface IgnoredRowView {
  conceptId: number;
  label: string;
  kind?: "topic" | "word";
}

/** Props of the ignored list: the rows, and the concept restored last (its Undo stays until the next action). */
export interface IgnoredListProps {
  rows: IgnoredRowView[];
  restored?: IgnoredRowView;
}

/** Handlers of the ignored list. Restore and Undo call the ignored client; Back is hidden without it. */
export interface IgnoredListHandlers {
  onRestore: (conceptId: number) => void | Promise<void>;
  onUndo: (conceptId: number) => void | Promise<void>;
  onBack?: () => void;
}

/**
 * Ignored words and topics: "Nothing is ignored." when the list is empty, else one row per concept with
 * Restore. After a restore, "Restored." with Undo shows for that concept.
 */
export function renderIgnoredList(props: IgnoredListProps, handlers: IgnoredListHandlers): HTMLElement {
  const screen = el("section", undefined, "ignored-list");
  screen.append(el("h2", TITLE), el("p", NOTE, "note"));
  if (props.rows.length === 0) {
    screen.append(el("p", EMPTY, "empty"));
  } else {
    const list = el("ul");
    for (const row of props.rows) {
      const item = el("li", undefined, "ignored-row");
      item.append(el("span", row.label, "label"));
      if (row.kind !== undefined) {
        item.append(el("span", row.kind === "topic" ? TOPIC : WORD, "kind"));
      }
      // A failed restore keeps the row in place; the rejection is caught so no unhandled rejection is raised.
      const restore = async () => {
        try {
          await handlers.onRestore(row.conceptId);
        } catch {
          // The core call failed: the row stays, no new copy is shown (copy approval pending).
        }
      };
      item.append(button(RESTORE, () => void restore(), "restore"));
      list.append(item);
    }
    screen.append(list);
  }
  if (props.restored !== undefined) {
    const restored = props.restored;
    const line = el("p", undefined, "restored");
    line.append(el("span", `${RESTORED} ${restored.label}`, "restored-text"));
    // A failed Undo rejects; the catch keeps the "Restored." line in place, so no unhandled rejection is raised.
    const undo = async () => {
      try {
        await handlers.onUndo(restored.conceptId);
      } catch {
        // The core call failed: the Restored line stays.
      }
    };
    line.append(button(TEXT_UNDO, () => void undo(), "undo"));
    screen.append(line);
  }
  if (handlers.onBack) {
    screen.append(button(BACK, () => handlers.onBack?.(), "back"));
  }
  return screen;
}
