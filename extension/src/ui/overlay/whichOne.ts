import type { CoreClient } from "../../coreClient";
import type { ScanConceptCandidate } from "../../coreClientTypes";
import { el } from "../dom";
import { TEXT_HL_WHICH_ONE } from "../strings";

export interface WhichOneOptions {
  topicId: number;
  word: string;
  candidates: ScanConceptCandidate[];
  client: Pick<CoreClient, "chooseConcept">;
  /** Runs after the choice is remembered for this page topic. */
  onPick: (candidate: ScanConceptCandidate) => void | Promise<void>;
}

/**
 * "Which one?" list: every concept the written word can mean. Picking one remembers it for this
 * page topic (chooseConcept), then calls onPick. A failed choice shows its error under the list.
 */
export function renderWhichOne(opts: WhichOneOptions): HTMLElement {
  const root = el("div", undefined, "hl-which-one");
  root.append(el("h2", TEXT_HL_WHICH_ONE[0], "title"));
  // The inventory sample ends in "window"; the real word replaces it.
  root.append(el("p", TEXT_HL_WHICH_ONE[4].split("window").join(opts.word), "word"));
  const list = el("ul", undefined, "candidates");
  const note = el("p", undefined, "note");
  for (const candidate of opts.candidates) {
    const item = el("li");
    const button = el("button", candidate.label, "candidate");
    button.type = "button";
    button.addEventListener("click", () => {
      note.textContent = "";
      new Promise<void>((resolve) => resolve(opts.client.chooseConcept(opts.topicId, opts.word, candidate.conceptId)))
        .then(() => opts.onPick(candidate))
        .catch((err: unknown) => {
          note.textContent = err instanceof Error ? err.message : String(err);
        });
    });
    item.append(button);
    list.append(item);
  }
  root.append(list, note);
  return root;
}
