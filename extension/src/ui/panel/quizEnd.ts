import type { ReviewState } from "../../messages";
import { el } from "../dom";
import { TEXT_QUIZ_END } from "../strings";

const [MARK_NEW, TITLE, NOTE, MARK_KNOWN, SUMMARY, ADD_TO_LIST, DONE, NOT_SYNCED] = TEXT_QUIZ_END;

/** One concept of the quiz result: its id, label and whether the core has the mark. */
export interface QuizEndConcept {
  id: number;
  label: string;
  synced: boolean;
}

/** Props of the quiz-end screen: the concepts the quiz touched, in order. */
export interface QuizEndProps {
  concepts: QuizEndConcept[];
}

/** User actions of the quiz end: a concept state change, and Done. */
export interface QuizEndActions {
  onSet(conceptId: number, state: ReviewState): Promise<void>;
  /** Add to list: opens the list picker for the concept. */
  onAddToList(conceptId: number): void;
  /** The summary button of the mini quiz result. */
  onSummary(): void;
  onDone(): void;
}

/**
 * Quiz result: the title, the note that right answers move New concepts to Learning, one row per
 * concept with Mark as New and Mark as Known, a Not synced badge for unsynced marks, and Done.
 */
export function renderQuizEnd(props: QuizEndProps, actions: QuizEndActions): HTMLElement {
  const screen = el("section", undefined, "quiz-end");
  screen.append(el("h2", TITLE), el("p", NOTE, "note"));
  const list = el("ul", undefined, "concepts");
  for (const concept of props.concepts) {
    const row = el("li", undefined, "concept");
    row.append(el("span", concept.label, "label"));
    // A failed mark shows the Not synced badge once, the same as a mark the core never saved.
    const showNotSynced = (): void => {
      if (row.querySelector(".badge") === null) row.append(el("span", NOT_SYNCED, "badge"));
    };
    const clearNotSynced = (): void => row.querySelector(".badge")?.remove();
    for (const [text, state] of [
      [MARK_NEW, "new"],
      [MARK_KNOWN, "known"],
    ] as const) {
      const choice = el("button", text, "mark");
      choice.type = "button";
      choice.addEventListener("click", () => {
        actions.onSet(concept.id, state).then(clearNotSynced, showNotSynced);
      });
      row.append(choice);
    }
    const add = el("button", ADD_TO_LIST, "add-to-list");
    add.type = "button";
    add.addEventListener("click", () => actions.onAddToList(concept.id));
    row.append(add);
    if (!concept.synced) showNotSynced();
    list.append(row);
  }
  screen.append(list);
  const summary = el("button", SUMMARY, "summary");
  summary.type = "button";
  summary.addEventListener("click", () => actions.onSummary());
  screen.append(summary);
  const done = el("button", DONE, "done");
  done.type = "button";
  done.addEventListener("click", () => actions.onDone());
  screen.append(done);
  return screen;
}
