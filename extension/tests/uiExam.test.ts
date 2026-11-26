import { describe, expect, it, vi } from "vitest";
import type { ExamResult } from "../src/coreClientTypes";
import { renderExamResult } from "../src/ui/panel/examResult";
import { positionText, renderExamRun } from "../src/ui/panel/examRun";
import { TEXT_EXAM_RESULT, TEXT_EXAM_RUN } from "../src/ui/strings";

const RUN_HANDLERS = () => ({ onAnswer: vi.fn(), onNext: vi.fn(), onFinish: vi.fn(), onLeave: vi.fn() });
const RESULT_HANDLERS = () => ({ onConfirm: vi.fn(), onOpenItems: vi.fn() });

function buttonWith(root: HTMLElement, label: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((b) => b.textContent === label);
  if (!found) throw new Error(`no button ${label}`);
  return found;
}

const QUESTION = {
  kind: "question" as const,
  index: 2,
  total: 10,
  prompt: "Which flag starts the handshake?",
  choices: ["SYN", "ACK", "FIN"],
  selected: null,
  last: false,
};

describe("exam run, one test per inventory state", () => {
  it("question: shows the position, source, prompt and choices; Next follows", () => {
    const handlers = RUN_HANDLERS();
    const box = renderExamRun(QUESTION, handlers);
    expect(box.querySelector("h2")?.textContent).toBe(TEXT_EXAM_RUN[0]);
    expect(box.querySelector(".exam-position")?.textContent).toBe("Question 2 of 10");
    expect(box.querySelector(".exam-source")?.textContent).toBe(TEXT_EXAM_RUN[2]);
    expect(box.querySelector(".exam-prompt")?.textContent).toBe(QUESTION.prompt);
    expect(box.querySelectorAll(".exam-choices input[type=radio]")).toHaveLength(3);
    buttonWith(box, TEXT_EXAM_RUN[3]).click();
    expect(handlers.onNext).toHaveBeenCalledTimes(1);
  });

  it("position text fills index and total into the pinned template", () => {
    expect(positionText(2, 10)).toBe("Question 2 of 10");
    expect(positionText(10, 10)).toBe("Question 10 of 10");
  });

  it("question: choosing a radio reports its index", () => {
    const handlers = RUN_HANDLERS();
    const box = renderExamRun(QUESTION, handlers);
    const radios = box.querySelectorAll<HTMLInputElement>(".exam-choices input[type=radio]");
    radios[1].checked = true;
    radios[1].dispatchEvent(new Event("change"));
    expect(handlers.onAnswer).toHaveBeenCalledWith(1);
  });

  it("last question: shows Finish exam instead of Next and calls onFinish", () => {
    const handlers = RUN_HANDLERS();
    const box = renderExamRun({ ...QUESTION, last: true }, handlers);
    expect(box.querySelector("button[class=exam-next]")).toBeNull();
    buttonWith(box, TEXT_EXAM_RUN[4]).click();
    expect(handlers.onFinish).toHaveBeenCalledTimes(1);
  });

  it("error: shows Could not load the exam. and Leave exam calls onLeave", () => {
    const handlers = RUN_HANDLERS();
    const box = renderExamRun({ kind: "error" }, handlers);
    expect(box.querySelector(".exam-error")?.textContent).toBe(TEXT_EXAM_RUN[6]);
    buttonWith(box, TEXT_EXAM_RUN[5]).click();
    expect(handlers.onLeave).toHaveBeenCalledTimes(1);
  });

  it("focus off: shows the focus-mode notice and no question", () => {
    const box = renderExamRun({ kind: "focus-off" }, RUN_HANDLERS());
    expect(box.querySelector(".exam-focus-off")?.textContent).toBe(TEXT_EXAM_RUN[7]);
    expect(box.querySelector(".exam-prompt")).toBeNull();
  });
});

const RESULT: ExamResult = {
  id: 7,
  origin: "web",
  taken_at: "2026-11-26T10:00:00Z",
  passed: true,
  score: 0.8,
  status: "pending",
  concepts: [
    { concept_id: 1, correct: true, confirmed: false },
    { concept_id: 2, correct: true, confirmed: true },
    { concept_id: 3, correct: false, confirmed: false },
  ],
};

describe("exam result, one test per inventory state", () => {
  it("loaded: lists right answers under Known and wrong ones under Needs practice", () => {
    const box = renderExamResult({ result: RESULT, names: new Map([[1, "SYN"], [3, "FIN"]]) }, RESULT_HANDLERS());
    expect(box.querySelector("h2")?.textContent).toBe(TEXT_EXAM_RESULT[0]);
    expect(box.querySelector(".exam-known-heading")?.textContent).toBe(TEXT_EXAM_RESULT[1]);
    expect(box.querySelector(".exam-needs-heading")?.textContent).toBe(TEXT_EXAM_RESULT[2]);
    expect(box.querySelector(".exam-known-explain")?.textContent).toBe(TEXT_EXAM_RESULT[3]);
    expect([...box.querySelectorAll(".exam-known li")].map((li) => li.textContent)).toEqual(["SYN", "#2"]);
    expect([...box.querySelectorAll(".exam-needs li")].map((li) => li.textContent)).toEqual(["FIN"]);
  });

  it("loaded: Open course items sends the wrong concept ids", () => {
    const handlers = RESULT_HANDLERS();
    const box = renderExamResult({ result: RESULT }, handlers);
    buttonWith(box, TEXT_EXAM_RESULT[4]).click();
    expect(handlers.onOpenItems).toHaveBeenCalledWith([3]);
  });

  it("loaded: no wrong answers means no Needs practice block", () => {
    const allRight: ExamResult = { ...RESULT, concepts: [{ concept_id: 1, correct: true, confirmed: false }] };
    const box = renderExamResult({ result: allRight }, RESULT_HANDLERS());
    expect(box.querySelector(".exam-needs-heading")).toBeNull();
    expect(box.querySelector(".exam-open-items")).toBeNull();
  });

  it("error: shows Could not load the result. and no confirm button", () => {
    const box = renderExamResult({ result: null }, RESULT_HANDLERS());
    expect(box.querySelector(".exam-result-error")?.textContent).toBe(TEXT_EXAM_RESULT[6]);
    expect(box.querySelector(".exam-done")).toBeNull();
  });

  it("D58: rendering and every other click write no mark; only Done confirms the pending right answers", () => {
    const handlers = RESULT_HANDLERS();
    const box = renderExamResult({ result: RESULT }, handlers);
    expect(Object.keys(handlers).sort()).toEqual(["onConfirm", "onOpenItems"]);
    buttonWith(box, TEXT_EXAM_RESULT[4]).click();
    expect(handlers.onConfirm).not.toHaveBeenCalled();
    buttonWith(box, TEXT_EXAM_RESULT[5]).click();
    expect(handlers.onConfirm).toHaveBeenCalledTimes(1);
    expect(handlers.onConfirm).toHaveBeenCalledWith([1]);
  });
});
