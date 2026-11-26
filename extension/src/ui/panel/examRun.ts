import { button, el } from "../dom";
import { TEXT_EXAM_RUN } from "../strings";

const [TITLE, QUESTION_OF, SOURCE, NEXT, FINISH, LEAVE, LOAD_FAILED, FOCUS_OFF] = TEXT_EXAM_RUN;

/** Position text "Question <index> of <total>" from the pinned template; throws if the template changes shape. */
export function positionText(index: number, total: number): string {
  const pattern = /\d+ of \d+$/;
  if (!pattern.test(QUESTION_OF)) throw new Error(`exam position template has no "N of M" tail: ${QUESTION_OF}`);
  return QUESTION_OF.replace(pattern, `${index} of ${total}`);
}

/** One exam state: a question, a load error, or focus mode off (the exam needs it on). */
export type ExamRunProps =
  | { kind: "question"; index: number; total: number; prompt: string; choices: string[]; selected: number | null; last: boolean }
  | { kind: "error" }
  | { kind: "focus-off" };

/** Callbacks of the exam run screen. The screen writes no marks; the result screen does, on confirm. */
export interface ExamRunHandlers {
  onAnswer(choice: number): void;
  onNext(): void;
  onFinish(): void;
  onLeave(): void;
}

/** Exam run: one question at a time with its choices, Next or Finish, and Leave exam. */
export function renderExamRun(props: ExamRunProps, handlers: ExamRunHandlers): HTMLElement {
  const box = el("section", undefined, "exam-run");
  box.append(el("h2", TITLE));
  if (props.kind === "error") {
    box.append(el("p", LOAD_FAILED, "exam-error"));
  } else if (props.kind === "focus-off") {
    box.append(el("p", FOCUS_OFF, "exam-focus-off"));
  } else {
    box.append(el("p", positionText(props.index, props.total), "exam-position"));
    box.append(el("p", SOURCE, "exam-source"));
    box.append(el("p", props.prompt, "exam-prompt"));
    const list = el("ol", undefined, "exam-choices");
    props.choices.forEach((text, i) => {
      const item = el("li");
      const label = el("label", text);
      const radio = el("input");
      radio.type = "radio";
      radio.name = "exam-choice";
      radio.checked = props.selected === i;
      radio.addEventListener("change", () => handlers.onAnswer(i));
      label.prepend(radio);
      item.append(label);
      list.append(item);
    });
    box.append(list);
    box.append(props.last ? button(FINISH, () => handlers.onFinish(), "exam-finish") : button(NEXT, () => handlers.onNext(), "exam-next"));
  }
  box.append(button(LEAVE, () => handlers.onLeave(), "exam-leave"));
  return box;
}
