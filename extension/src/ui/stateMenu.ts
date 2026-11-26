import type { ReviewState } from "../types";
import { el } from "./dom";

/** Menu order: New, Learning, Known. */
export const STATE_ORDER: readonly ReviewState[] = ["new", "learning", "known"];

const STATE_LABEL: Record<ReviewState, string> = { new: "New", learning: "Learning", known: "Known" };

/**
 * Row of icon-style state buttons in STATE_ORDER. The current state button has aria-pressed="true",
 * the others "false"; a null current marks none. Click calls onChoose with that state.
 */
export function renderStateMenu(
  current: ReviewState | null,
  onChoose: (state: ReviewState) => void | Promise<void>,
): HTMLElement {
  const menu = el("div", undefined, "state-menu");
  menu.setAttribute("role", "group");
  const note = el("span", undefined, "note");
  let clicks = 0;
  for (const state of STATE_ORDER) {
    const label = STATE_LABEL[state];
    const button = el("button", label, `state-button state-${state}`);
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", String(state === current));
    button.addEventListener("click", () => {
      note.textContent = "";
      clicks += 1;
      const click = clicks;
      // A rejected choice shows its error in the note, as the sidepanel course rows do.
      // A later click supersedes an earlier one, so only the latest click may write the note.
      new Promise<void>((resolve) => resolve(onChoose(state))).catch((err: unknown) => {
        if (click !== clicks) return;
        note.textContent = err instanceof Error ? err.message : String(err);
      });
    });
    menu.append(button);
  }
  menu.append(note);
  return menu;
}
