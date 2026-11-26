import { describe, expect, it, vi } from "vitest";
import { renderQuizEnd, type QuizEndActions } from "../src/ui/panel/quizEnd";
import { renderQuizRun, type QuizQuestion } from "../src/ui/panel/quizRun";
import { renderQuizPin } from "../src/ui/overlay/quizPin";
import { TEXT_INLINE_QUIZ_PIN, TEXT_QUIZ_END, TEXT_QUIZ_RUN } from "../src/ui/strings";

const QUESTION: QuizQuestion = {
  text: "What does SYN do?",
  choices: ["Opens a connection", "Closes a socket", "Sends a reset", "Pings a host"],
  quote: "SYN starts the handshake.",
};

const ACTIONS = { onNext: vi.fn(), onFinish: vi.fn(), onStop: vi.fn() };

/** Button with the given visible text inside root; fails the test when there is none. */
function buttonNamed(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text);
  if (found === undefined) throw new Error(`no button "${text}"`);
  return found;
}

describe("quiz run", () => {
  it("shows the question, its counter, choices and source line when ready", () => {
    const screen = renderQuizRun({ state: "ready", question: QUESTION, index: 2, total: 5 }, ACTIONS);
    // The counter text comes from the inventory entry; only its example numbers change.
    expect(screen.querySelector(".counter")?.textContent).toBe(TEXT_QUIZ_RUN[0].replace("1 of 5", "2 of 5"));
    expect(screen.querySelector(".question")?.textContent).toBe("What does SYN do?");
    expect(screen.querySelectorAll(".choice")).toHaveLength(4);
    expect(screen.querySelector(".source")?.textContent).toBe(`${TEXT_QUIZ_RUN[4]} ${TEXT_QUIZ_RUN[6]} · ${TEXT_QUIZ_RUN[5]}`);
    expect(screen.querySelector(".quote")?.textContent).toBe("SYN starts the handshake.");
  });

  it("offers Next before the last question and Finish on it", () => {
    const actions = { onNext: vi.fn(), onFinish: vi.fn(), onStop: vi.fn() };
    const screen = renderQuizRun({ state: "ready", question: QUESTION, index: 1, total: 5 }, actions);
    buttonNamed(screen, TEXT_QUIZ_RUN[1]).click();
    expect(actions.onNext).toHaveBeenCalledOnce();
    const last = renderQuizRun({ state: "ready", question: QUESTION, index: 5, total: 5 }, actions);
    buttonNamed(last, TEXT_QUIZ_RUN[2]).click();
    expect(actions.onFinish).toHaveBeenCalledOnce();
  });

  it("always shows Stop quiz and calls onStop", () => {
    const actions = { onNext: vi.fn(), onFinish: vi.fn(), onStop: vi.fn() };
    const screen = renderQuizRun({ state: "ready", question: QUESTION, index: 2, total: 5 }, actions);
    buttonNamed(screen, TEXT_QUIZ_RUN[3]).click();
    expect(actions.onStop).toHaveBeenCalledOnce();
  });

  it("shows the writing line while loading and no question", () => {
    const screen = renderQuizRun({ state: "loading", index: 1, total: 5 }, ACTIONS);
    expect(screen.querySelector(".status")?.textContent).toBe(TEXT_QUIZ_RUN[9]);
    expect(screen.querySelector(".question")).toBeNull();
  });

  it("shows the could-not-write line on error", () => {
    const screen = renderQuizRun({ state: "error", index: 1, total: 5 }, ACTIONS);
    expect(screen.querySelector(".status")?.textContent).toBe(TEXT_QUIZ_RUN[7]);
  });

  it("shows the server-down line offline and still offers Stop quiz", () => {
    const screen = renderQuizRun({ state: "offline", index: 1, total: 5 }, ACTIONS);
    expect(screen.querySelector(".status")?.textContent).toBe(TEXT_QUIZ_RUN[8]);
    expect(buttonNamed(screen, TEXT_QUIZ_RUN[3])).toBeDefined();
  });
});

/** Quiz-end actions with no-op defaults; each test overrides what it checks. */
function end(over: Partial<QuizEndActions> = {}): QuizEndActions {
  return { onSet: vi.fn(async () => {}), onAddToList: vi.fn(), onSummary: vi.fn(), onDone: vi.fn(), ...over };
}

describe("quiz end", () => {
  const concepts = [
    { id: 7, label: "SYN", synced: true },
    { id: 9, label: "ACK", synced: false },
  ];

  it("shows the title, note and one row per concept", () => {
    const screen = renderQuizEnd({ concepts }, end());
    expect(screen.querySelector("h2")?.textContent).toBe(TEXT_QUIZ_END[1]);
    expect(screen.querySelector(".note")?.textContent).toBe(TEXT_QUIZ_END[2]);
    expect(screen.querySelectorAll(".concept")).toHaveLength(2);
  });

  it("shows Not synced only for unsynced marks", () => {
    const screen = renderQuizEnd({ concepts }, end());
    const badges = [...screen.querySelectorAll(".concept")].map((row) => row.querySelector(".badge")?.textContent ?? null);
    expect(badges).toEqual([null, TEXT_QUIZ_END[7]]);
  });

  it("sends the concept id and state from Mark as New and Mark as Known", () => {
    const onSet = vi.fn(async () => {});
    const screen = renderQuizEnd({ concepts }, end({ onSet }));
    const firstRow = screen.querySelector(".concept") as HTMLElement;
    buttonNamed(firstRow, TEXT_QUIZ_END[0]).click();
    buttonNamed(firstRow, TEXT_QUIZ_END[3]).click();
    expect(onSet).toHaveBeenNthCalledWith(1, 7, "new");
    expect(onSet).toHaveBeenNthCalledWith(2, 7, "known");
  });

  it("shows Not synced on a row whose mark the core rejects", async () => {
    const onSet = vi.fn(() => Promise.reject(new Error("core down")));
    const screen = renderQuizEnd({ concepts: [concepts[0]] }, end({ onSet }));
    const row = screen.querySelector(".concept") as HTMLElement;
    expect(row.querySelector(".badge")).toBeNull();
    buttonNamed(row, TEXT_QUIZ_END[3]).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(onSet).toHaveBeenCalledOnce();
    expect(row.querySelector(".badge")?.textContent).toBe(TEXT_QUIZ_END[7]);
    buttonNamed(row, TEXT_QUIZ_END[0]).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(row.querySelectorAll(".badge")).toHaveLength(1);
  });

  it("clears Not synced after a successful mark", async () => {
    const screen = renderQuizEnd({ concepts: [concepts[1]] }, end());
    const row = screen.querySelector(".concept") as HTMLElement;
    expect(row.querySelector(".badge")).not.toBeNull();
    buttonNamed(row, TEXT_QUIZ_END[3]).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(row.querySelector(".badge")).toBeNull();
  });

  it("calls onAddToList with the concept id from Add to list", () => {
    const onAddToList = vi.fn();
    const screen = renderQuizEnd({ concepts }, end({ onAddToList }));
    buttonNamed(screen.querySelectorAll<HTMLElement>(".concept")[1], TEXT_QUIZ_END[5]).click();
    expect(onAddToList).toHaveBeenCalledWith(9);
  });

  it("shows the summary button text from the inventory and calls onSummary", () => {
    const onSummary = vi.fn();
    const screen = renderQuizEnd({ concepts }, end({ onSummary }));
    buttonNamed(screen, TEXT_QUIZ_END[4]).click();
    expect(onSummary).toHaveBeenCalledOnce();
  });

  it("calls onDone from Done", () => {
    const onDone = vi.fn();
    const screen = renderQuizEnd({ concepts: [] }, end({ onDone }));
    buttonNamed(screen, TEXT_QUIZ_END[6]).click();
    expect(onDone).toHaveBeenCalledOnce();
  });
});

describe("section quiz pin", () => {
  const start = () => ({ onStart: vi.fn() });

  it("shows the pin with its label and question count when ready", () => {
    const card = renderQuizPin(document, { newConceptCount: 3, focus: false, offline: false }, start());
    expect(card).not.toBeNull();
    const button = card?.querySelector("button");
    expect(button?.textContent).toBe(TEXT_INLINE_QUIZ_PIN[0]);
    expect(button?.disabled).toBe(false);
    expect(card?.querySelector(".quiz-pin-count")?.textContent).toBe(TEXT_INLINE_QUIZ_PIN[1]);
  });

  it("hides the pin in focus mode", () => {
    expect(renderQuizPin(document, { newConceptCount: 3, focus: true, offline: false }, start())).toBeNull();
  });

  it("hides the pin when the section has no new concepts", () => {
    expect(renderQuizPin(document, { newConceptCount: 0, focus: false, offline: false }, start())).toBeNull();
  });

  it("disables the button and shows the server-down line offline", () => {
    const card = renderQuizPin(document, { newConceptCount: 3, focus: false, offline: true }, start());
    expect(card?.querySelector("button")?.disabled).toBe(true);
    expect(card?.querySelector(".menu-status")?.textContent).toBe(TEXT_QUIZ_RUN[8]);
  });

  it("calls onStart when the button is clicked", () => {
    const actions = start();
    const card = renderQuizPin(document, { newConceptCount: 3, focus: false, offline: false }, actions);
    card?.querySelector("button")?.click();
    expect(actions.onStart).toHaveBeenCalledOnce();
  });
});
