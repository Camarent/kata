/**
 * Section quiz pin: the inline offer on a page section ("Quiz this section" with its question
 * count). Hidden in focus mode and when the section has no new concepts. Text comes from the
 * approved strings.
 */
import { TEXT_INLINE_QUIZ_PIN, TEXT_QUIZ_RUN } from "../strings";
import { menuButton, statusParagraph } from "./blockMenu";

const [LABEL, COUNT] = TEXT_INLINE_QUIZ_PIN;
const OFFLINE = TEXT_QUIZ_RUN[8];

/** Inputs of the section quiz pin: the section's new concept count, focus mode and the core state. */
export interface QuizPinProps {
  newConceptCount: number;
  focus: boolean;
  offline: boolean;
}

/** Callback of the section quiz pin: start a mini quiz for this section only. */
export interface QuizPinActions {
  onStart(): void;
}

/**
 * Section quiz pin card: "Quiz this section" with "5 questions", and the offline notice with the
 * button disabled. Returns null in focus mode (no inline quiz offers) or with no new concepts.
 */
export function renderQuizPin(doc: Document, props: QuizPinProps, actions: QuizPinActions): HTMLElement | null {
  if (props.focus || props.newConceptCount <= 0) return null;
  const card = doc.createElement("div");
  card.className = "quiz-pin";
  const start = menuButton(doc, LABEL, "btn", () => actions.onStart(), props.offline);
  const count = doc.createElement("p");
  count.className = "quiz-pin-count";
  count.textContent = COUNT;
  card.append(start, count, statusParagraph(doc, props.offline ? OFFLINE : null));
  return card;
}
