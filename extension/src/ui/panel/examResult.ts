import type { ExamResult } from "../../coreClientTypes";
import { button, el } from "../dom";
import { TEXT_EXAM_RESULT } from "../strings";

const [TITLE, KNOWN, NEEDS_PRACTICE, EXPLAIN, OPEN_ITEMS, DONE, LOAD_FAILED] = TEXT_EXAM_RESULT;

/** Props of the exam result screen: the stored result (null when it did not load) and optional concept names. */
export interface ExamResultProps {
  result: ExamResult | null;
  names?: ReadonlyMap<number, string>;
}

/**
 * Callbacks of the exam result screen. D58: nothing is marked until the user presses Done;
 * onConfirm gets the ids of the right answers still awaiting confirmation (the only writes).
 */
export interface ExamResultHandlers {
  onConfirm(conceptIds: number[]): void;
  onOpenItems(conceptIds: number[]): void;
}

/**
 * Exam result: right answers under Known (confirmed by Done), wrong ones under Needs practice
 * with a link to their course items. Wrong concepts stay Learning; nothing is lowered.
 */
export function renderExamResult(props: ExamResultProps, handlers: ExamResultHandlers): HTMLElement {
  const box = el("section", undefined, "exam-result");
  box.append(el("h2", TITLE));
  if (props.result === null) {
    box.append(el("p", LOAD_FAILED, "exam-result-error"));
    return box;
  }
  const name = (id: number) => props.names?.get(id) ?? `#${id}`;
  const right = props.result.concepts.filter((c) => c.correct);
  const wrong = props.result.concepts.filter((c) => !c.correct);
  const pending = right.filter((c) => !c.confirmed).map((c) => c.concept_id);

  box.append(el("h3", KNOWN, "exam-known-heading"));
  box.append(el("p", EXPLAIN, "exam-known-explain"));
  const knownList = el("ul", undefined, "exam-known");
  for (const c of right) knownList.append(el("li", name(c.concept_id)));
  box.append(knownList);

  if (wrong.length > 0) {
    box.append(el("h3", NEEDS_PRACTICE, "exam-needs-heading"));
    const needsList = el("ul", undefined, "exam-needs");
    for (const c of wrong) needsList.append(el("li", name(c.concept_id)));
    box.append(needsList);
    const wrongIds = wrong.map((c) => c.concept_id);
    box.append(button(OPEN_ITEMS, () => handlers.onOpenItems(wrongIds), "exam-open-items"));
  }
  box.append(button(DONE, () => handlers.onConfirm(pending), "exam-done"));
  return box;
}
