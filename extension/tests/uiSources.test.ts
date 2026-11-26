import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderExamEntry } from "../src/ui/panel/examEntry";
import { renderExamProposals } from "../src/ui/panel/examProposals";
import { renderSourceAdd, type SourceAddHandlers } from "../src/ui/panel/sourceAdd";
import { renderSourceConfirm } from "../src/ui/panel/sourceConfirm";
import { TEXT_EXAM_RESULT_ENTRY, TEXT_EXAM_RESULT_PROPOSALS, TEXT_SOURCE_ADD, TEXT_SOURCE_CONFIRM_TREE } from "../src/ui/strings";

/** Button with the given visible text inside root; fails the test when there is none. */
function buttonNamed(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text);
  if (found === undefined) throw new Error(`no button "${text}"`);
  return found;
}

/** Text of every element of root matching the selector, in document order. */
function textsOf(root: HTMLElement, selector: string): (string | null)[] {
  return [...root.querySelectorAll(selector)].map((node) => node.textContent);
}

describe("source and exam screens, one test per inventory state", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  describe("add source", () => {
    const [TITLE, PASTE, CHOOSE_FILE, USE_PAGE, USE_COURSE, SUBMIT, CANCEL, READING, FAILED, NOT_TEACHING] = TEXT_SOURCE_ADD;
    const handlers = (): SourceAddHandlers => ({
      onPasteText: vi.fn(),
      onChooseFile: vi.fn(),
      onUsePage: vi.fn(),
      onUseCourse: vi.fn(),
      onAddSource: vi.fn(),
      onCancel: vi.fn(),
    });

    it("idle: title, the four ways to give a source, Add source and Cancel", () => {
      root.append(renderSourceAdd({ status: "idle" }, handlers()));
      expect(textsOf(root, "h2")).toEqual([TITLE]);
      expect(textsOf(root, "button")).toEqual([PASTE, CHOOSE_FILE, USE_PAGE, USE_COURSE, SUBMIT, CANCEL]);
      expect(root.querySelector(".status")).toBeNull();
    });

    it("idle: each option and submit calls its own handler on click only", () => {
      const h = handlers();
      root.append(renderSourceAdd({ status: "idle" }, h));
      buttonNamed(root, PASTE).click();
      buttonNamed(root, CHOOSE_FILE).click();
      buttonNamed(root, USE_PAGE).click();
      buttonNamed(root, USE_COURSE).click();
      buttonNamed(root, SUBMIT).click();
      buttonNamed(root, CANCEL).click();
      expect(h.onPasteText).toHaveBeenCalledTimes(1);
      expect(h.onChooseFile).toHaveBeenCalledTimes(1);
      expect(h.onUsePage).toHaveBeenCalledTimes(1);
      expect(h.onUseCourse).toHaveBeenCalledTimes(1);
      expect(h.onAddSource).toHaveBeenCalledTimes(1);
      expect(h.onCancel).toHaveBeenCalledTimes(1);
    });

    it("reading: shows Reading the source... and disables the options and submit", () => {
      root.append(renderSourceAdd({ status: "reading" }, handlers()));
      expect(textsOf(root, ".status")).toEqual([READING]);
      expect(buttonNamed(root, SUBMIT).disabled).toBe(true);
      expect(buttonNamed(root, PASTE).disabled).toBe(true);
      expect(buttonNamed(root, CANCEL).disabled).toBe(false);
    });

    it("failed: shows Could not read this source.", () => {
      root.append(renderSourceAdd({ status: "failed" }, handlers()));
      expect(textsOf(root, ".error")).toEqual([FAILED]);
    });

    it("not teaching: shows Nothing here looks like teaching content.", () => {
      root.append(renderSourceAdd({ status: "not-teaching" }, handlers()));
      expect(textsOf(root, ".status")).toEqual([NOT_TEACHING]);
    });
  });

  describe("confirm new topics", () => {
    const [TITLE, NOTE, REMOVE, ADD, CANCEL, FAILED] = TEXT_SOURCE_CONFIRM_TREE;

    it("lists each proposed topic with Remove, the note, Add to track and Cancel", () => {
      root.append(renderSourceConfirm({ topics: ["Ratios", "Rates"], failed: false }, { onRemove: vi.fn(), onAddToTrack: vi.fn(), onCancel: vi.fn() }));
      expect(textsOf(root, "h2")).toEqual([TITLE]);
      expect(textsOf(root, ".label")).toEqual(["Ratios", "Rates"]);
      expect(textsOf(root, "button")).toEqual([REMOVE, REMOVE, ADD, CANCEL]);
      expect(textsOf(root, ".note")).toEqual([NOTE]);
    });

    it("Remove calls onRemove with that topic's index; Add to track and Cancel call their handlers", () => {
      const h = { onRemove: vi.fn(), onAddToTrack: vi.fn(), onCancel: vi.fn() };
      root.append(renderSourceConfirm({ topics: ["Ratios", "Rates"], failed: false }, h));
      root.querySelectorAll<HTMLButtonElement>(".remove")[1].click();
      expect(h.onRemove).toHaveBeenCalledWith(1);
      expect(h.onAddToTrack).not.toHaveBeenCalled();
      buttonNamed(root, ADD).click();
      buttonNamed(root, CANCEL).click();
      expect(h.onAddToTrack).toHaveBeenCalledTimes(1);
      expect(h.onCancel).toHaveBeenCalledTimes(1);
    });

    it("no topics left: Add to track is disabled", () => {
      root.append(renderSourceConfirm({ topics: [], failed: false }, { onRemove: vi.fn(), onAddToTrack: vi.fn(), onCancel: vi.fn() }));
      expect(buttonNamed(root, ADD).disabled).toBe(true);
    });

    it("failed: shows Could not read this source. and no topic list", () => {
      root.append(renderSourceConfirm({ topics: ["Ratios"], failed: true }, { onRemove: vi.fn(), onAddToTrack: vi.fn(), onCancel: vi.fn() }));
      expect(textsOf(root, ".error")).toEqual([FAILED]);
      expect(root.querySelector("ul")).toBeNull();
      expect(buttonNamed(root, ADD).disabled).toBe(true);
    });
  });

  describe("exam result entry", () => {
    const [TITLE, DATE, PASSED, NOT_PASSED, SCORE, DOMAINS_LABEL, ADD_DOMAIN, SAVE, CANCEL, FAILED] = TEXT_EXAM_RESULT_ENTRY;

    it("idle: title, date, Passed, Not passed, score, optional domain scores, Save result and Cancel", () => {
      root.append(renderExamEntry({ failed: false }, { onSave: vi.fn(async () => {}), onCancel: vi.fn() }));
      expect(textsOf(root, "h2")).toEqual([TITLE]);
      expect(textsOf(root, "label")).toEqual([DATE, PASSED, NOT_PASSED, SCORE]);
      expect(textsOf(root, ".domains-label")).toEqual([DOMAINS_LABEL]);
      expect(textsOf(root, "button")).toEqual([ADD_DOMAIN, SAVE, CANCEL]);
      expect(root.querySelector(".error")?.textContent).toBe("");
    });

    it("Add domain score adds one domain row of name and score inputs", () => {
      root.append(renderExamEntry({ failed: false }, { onSave: vi.fn(async () => {}), onCancel: vi.fn() }));
      buttonNamed(root, ADD_DOMAIN).click();
      expect(root.querySelectorAll(".domains input")).toHaveLength(2);
    });

    it("Save result sends the entered values once", async () => {
      const onSave = vi.fn(async () => {});
      root.append(renderExamEntry({ failed: false }, { onSave, onCancel: vi.fn() }));
      const inputs = root.querySelectorAll<HTMLInputElement>("input");
      const [date, passed, , score] = [inputs[0], inputs[1], inputs[2], inputs[3]];
      date.value = "2026-11-01";
      passed.checked = true;
      score.value = " 82 ";
      buttonNamed(root, SAVE).click();
      await vi.waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
      expect(onSave).toHaveBeenCalledWith({ date: "2026-11-01", passed: true, score: "82", domains: [] });
    });

    it("rejected save: shows Could not save the result. and keeps the form", async () => {
      const onSave = vi.fn(async () => {
        throw new Error("down");
      });
      root.append(renderExamEntry({ failed: false }, { onSave, onCancel: vi.fn() }));
      buttonNamed(root, SAVE).click();
      await vi.waitFor(() => expect(root.querySelector(".error")?.textContent).toBe(FAILED));
      expect(buttonNamed(root, SAVE).disabled).toBe(false);
      expect(root.querySelectorAll("input")).toHaveLength(4);
    });

    it("failed prop: shows Could not save the result. at once", () => {
      root.append(renderExamEntry({ failed: true }, { onSave: vi.fn(async () => {}), onCancel: vi.fn() }));
      expect(textsOf(root, ".error")).toEqual([FAILED]);
    });
  });

  describe("concepts to review", () => {
    const [TITLE, NOTE, MOVE, KEEP, PICK_BY_HAND, DONE, NO_SCORES, FAILED] = TEXT_EXAM_RESULT_PROPOSALS;
    const proposals = [
      { conceptId: 1, label: "Ratio", domain: "Maths" },
      { conceptId: 2, label: "Rate", domain: "Maths" },
    ];

    it("lists each proposal with Move to Learning and Keep Known, then Done and Pick topics by hand", () => {
      root.append(renderExamProposals({ proposals, failed: false }, { onDone: vi.fn(), onPickByHand: vi.fn() }));
      expect(textsOf(root, "h2")).toEqual([TITLE]);
      expect(textsOf(root, ".note")).toEqual([NOTE]);
      expect(textsOf(root, ".label")).toEqual(["Ratio", "Rate"]);
      expect(textsOf(root, "button")).toEqual([MOVE, KEEP, MOVE, KEEP, DONE, PICK_BY_HAND]);
    });

    it("no mark is applied until Done: choosing Move does not call onDone", () => {
      const onDone = vi.fn();
      root.append(renderExamProposals({ proposals, failed: false }, { onDone, onPickByHand: vi.fn() }));
      root.querySelectorAll<HTMLButtonElement>(".move-to-learning")[0].click();
      expect(onDone).not.toHaveBeenCalled();
    });

    it("Done sends only the rows moved to Learning, Keep Known rows left out", () => {
      const onDone = vi.fn();
      root.append(renderExamProposals({ proposals, failed: false }, { onDone, onPickByHand: vi.fn() }));
      root.querySelectorAll<HTMLButtonElement>(".move-to-learning")[1].click();
      buttonNamed(root, DONE).click();
      expect(onDone).toHaveBeenCalledTimes(1);
      expect(onDone).toHaveBeenCalledWith([{ conceptId: 2, state: "learning" }]);
    });

    it("Keep Known after Move reverts the row, so Done sends nothing for it", () => {
      const onDone = vi.fn();
      root.append(renderExamProposals({ proposals, failed: false }, { onDone, onPickByHand: vi.fn() }));
      root.querySelectorAll<HTMLButtonElement>(".move-to-learning")[0].click();
      root.querySelectorAll<HTMLButtonElement>(".keep-known")[0].click();
      buttonNamed(root, DONE).click();
      expect(onDone).toHaveBeenCalledWith([]);
    });

    it("Pick topics by hand calls its handler and applies nothing", () => {
      const h = { onDone: vi.fn(), onPickByHand: vi.fn() };
      root.append(renderExamProposals({ proposals, failed: false }, h));
      buttonNamed(root, PICK_BY_HAND).click();
      expect(h.onPickByHand).toHaveBeenCalledTimes(1);
      expect(h.onDone).not.toHaveBeenCalled();
    });

    it("no domain scores: shows No domain scores were entered. and no rows", () => {
      root.append(renderExamProposals({ proposals: [], failed: false }, { onDone: vi.fn(), onPickByHand: vi.fn() }));
      expect(textsOf(root, ".status")).toEqual([NO_SCORES]);
      expect(root.querySelector("ul")).toBeNull();
    });

    it("failed load: shows Could not load the proposals.", () => {
      root.append(renderExamProposals({ proposals: [], failed: true }, { onDone: vi.fn(), onPickByHand: vi.fn() }));
      expect(textsOf(root, ".error")).toEqual([FAILED]);
    });
  });
});
