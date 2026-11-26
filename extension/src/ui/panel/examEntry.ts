import { button, el } from "../dom";
import { TEXT_EXAM_RESULT_ENTRY } from "../strings";

const [TITLE, DATE, PASSED, NOT_PASSED, SCORE, DOMAINS_LABEL, ADD_DOMAIN, SAVE, CANCEL, FAILED] = TEXT_EXAM_RESULT_ENTRY;

/** One domain score row of the exam form. */
export interface DomainScoreInput {
  domain: string;
  score: string;
}

/** What the exam form submits: date, result, overall score text and the optional domain scores. */
export interface ExamResultInput {
  date: string;
  passed: boolean;
  score: string;
  domains: DomainScoreInput[];
}

/** Props of the exam-result entry screen: whether the last save failed. */
export interface ExamEntryProps {
  failed: boolean;
}

/** Actions of the exam-result entry screen. onSave may reject; the screen then shows the save failure. */
export interface ExamEntryHandlers {
  onSave: (result: ExamResultInput) => Promise<void>;
  onCancel: () => void;
}

/**
 * Enter exam results: date, Passed or Not passed, overall score, optional domain scores added one
 * row at a time with Add domain score, then Save result and Cancel. Save sends the form once; a
 * rejected save shows "Could not save the result." and keeps the entered values.
 */
export function renderExamEntry(props: ExamEntryProps, handlers: ExamEntryHandlers): HTMLElement {
  const screen = el("section", undefined, "exam-entry");
  screen.append(el("h2", TITLE));
  const date = el("input");
  date.type = "date";
  date.name = "date";
  const passed = el("input");
  passed.type = "radio";
  passed.name = "passed";
  passed.value = "passed";
  const notPassed = el("input");
  notPassed.type = "radio";
  notPassed.name = "passed";
  notPassed.value = "not-passed";
  const score = el("input");
  score.type = "text";
  score.name = "score";
  screen.append(
    el("label", DATE),
    date,
    el("label", PASSED),
    passed,
    el("label", NOT_PASSED),
    notPassed,
    el("label", SCORE),
    score,
  );

  const domainsBox = el("div", undefined, "domains");
  const domainRows: { domain: HTMLInputElement; score: HTMLInputElement }[] = [];
  const addRow = () => {
    const domain = el("input");
    domain.type = "text";
    const domainScore = el("input");
    domainScore.type = "text";
    domainRows.push({ domain, score: domainScore });
    domainsBox.append(el("label", DOMAINS_LABEL), domain, domainScore);
  };
  screen.append(el("p", DOMAINS_LABEL, "domains-label"), domainsBox);
  screen.append(button(ADD_DOMAIN, addRow, "add-domain"));

  const error = el("p", props.failed ? FAILED : undefined, "error");
  error.setAttribute("role", "alert");
  const submit = async (save: HTMLButtonElement) => {
    save.disabled = true;
    try {
      await handlers.onSave({
        date: date.value,
        passed: passed.checked,
        score: score.value.trim(),
        domains: domainRows.map((row) => ({ domain: row.domain.value.trim(), score: row.score.value.trim() })),
      });
      error.textContent = "";
    } catch {
      error.textContent = FAILED;
    } finally {
      save.disabled = false;
    }
  };
  const save = button(SAVE, () => void submit(save), "save-result");
  screen.append(save, button(CANCEL, () => handlers.onCancel(), "cancel"), error);
  return screen;
}
