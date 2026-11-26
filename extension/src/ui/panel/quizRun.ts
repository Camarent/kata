import { el } from "../dom";
import { TEXT_QUIZ_RUN } from "../strings";

const [COUNTER, NEXT, FINISH, STOP, SOURCE, TIER, GENERAL, ERROR, OFFLINE, LOADING] = TEXT_QUIZ_RUN;

/** The counter line: the approved inventory text with its example numbers swapped for index and total. */
function counterLine(index: number, total: number): string {
  const values = [index, total];
  let next = 0;
  return COUNTER.replace(/\d+/g, () => String(values[next++]));
}

/** One question: its text, the 3-4 choices and the grounded source quote. */
export interface QuizQuestion {
  text: string;
  choices: string[];
  quote: string;
}

/** Quiz run state: loading and error show one status line; offline shows the off notice. */
export type QuizRunState = "ready" | "loading" | "error" | "offline";

/** Props of the quiz-run screen: the state, and the question shown when the state is ready. */
export interface QuizRunProps {
  state: QuizRunState;
  question?: QuizQuestion;
  index: number;
  total: number;
  /** Source label; "General reference" when the quiz has no fetched source. */
  sourceLabel?: string;
}

/** User actions of the quiz run; choosing a choice is the caller's concern. */
export interface QuizRunActions {
  onNext(): void;
  onFinish(): void;
  onStop(): void;
}

/** The status line of a non-ready state, or null when the state shows a question. */
function statusLine(state: QuizRunState): string | null {
  switch (state) {
    case "loading":
      return LOADING;
    case "error":
      return ERROR;
    case "offline":
      return OFFLINE;
    default:
      return null;
  }
}

/**
 * Quiz run: "Question i of n" with the question, its choices and the source line. Next moves on;
 * on the last question Next becomes Finish. Stop quiz always shows. Loading, error and offline
 * show one status line and no question.
 */
export function renderQuizRun(props: QuizRunProps, actions: QuizRunActions): HTMLElement {
  const screen = el("section", undefined, "quiz-run");
  const status = statusLine(props.state);
  if (status !== null || props.question === undefined) {
    screen.append(el("p", status ?? LOADING, "status"));
  } else {
    const question = props.question;
    screen.append(el("h2", counterLine(props.index, props.total), "counter"));
    screen.append(el("p", question.text, "question"));
    const list = el("ul", undefined, "choices");
    for (const choice of question.choices) {
      list.append(el("li", choice, "choice"));
    }
    screen.append(list);
    screen.append(el("p", `${SOURCE} ${props.sourceLabel ?? GENERAL} · ${TIER}`, "source"));
    screen.append(el("blockquote", question.quote, "quote"));
    const last = props.index >= props.total;
    const advance = el("button", last ? FINISH : NEXT, "advance");
    advance.type = "button";
    advance.addEventListener("click", () => (last ? actions.onFinish() : actions.onNext()));
    screen.append(advance);
  }
  const stop = el("button", STOP, "stop");
  stop.type = "button";
  stop.addEventListener("click", () => actions.onStop());
  screen.append(stop);
  return screen;
}
