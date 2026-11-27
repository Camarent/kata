// Test harness bundle for tests/browser/test_ui_flow.py: mounts the page overlay pieces that the
// content script does not wire yet (hover menu, Delete/Ignore with Undo, review tree, pin) on sample.html.
// Built with esbuild by the test fixture; it is never part of the extension.
import { renderReview } from "../../../extension/src/ui/panel/review";
import type { ReviewRow } from "../../../extension/src/messages";
import type { StorageArea } from "../../../extension/src/tokenStore";
import { CARD_CSS } from "../../../extension/src/ui/cardCss";
import { mountPin } from "../../../extension/src/ui/card/pin";
import { PinPositionStore } from "../../../extension/src/ui/card/pinPosition";
import { attachHlHover } from "../../../extension/src/ui/overlay/hlMenu";
import { renderConceptActions } from "../../../extension/src/ui/overlay/blockMenu";

const UNDO_WINDOW_MS = 3000;
const STORAGE_KEY = "harness.storage";
const START_X = 200;
const START_Y = 200;

type Bag = Record<string, unknown>;
const readBag = (): Bag => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Bag;

/** Storage area backed by the page's localStorage, so a pin position survives a reload. */
const storage: StorageArea = {
  async get(key) {
    const all = readBag();
    return key in all ? { [key]: all[key] } : {};
  },
  async set(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readBag(), ...items }));
  },
  async remove(key) {
    const all = readBag();
    delete all[key];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  },
};

const ROWS: ReviewRow[] = [
  { conceptId: 1, label: "Alpha", state: "new", evidence: "", area: "Area one" },
  { conceptId: 2, label: "Beta", state: "known", evidence: "", area: "Area two" },
];

const log: { states: string[]; commits: string[] } = { states: [], commits: [] };
(window as unknown as { harnessLog: typeof log }).harnessLog = log;

const root = document.getElementById("h") as HTMLElement;
const style = document.createElement("style");
style.textContent = CARD_CSS;
document.head.append(style);

attachHlHover(document.getElementById("word") as HTMLElement, {
  topicId: 1,
  word: "kata",
  item: { word: "kata", conceptId: 7, label: "Kata", definition: "A form.", state: "new", candidates: [] },
  offline: false,
  client: {
    chooseConcept: async () => undefined as never,
    reassignConcept: async () => undefined as never,
  },
  onState: (state) => {
    log.states.push(state);
  },
});

(document.getElementById("actions") as HTMLElement).append(
  renderConceptActions(document, {
    windowMs: UNDO_WINDOW_MS,
    onCommit: (action) => {
      log.commits.push(action);
    },
  }),
);

renderReview(document.getElementById("review") as HTMLElement, ROWS, { onSet: async () => undefined });

// The content script mounts its own pin at the bottom right; start this one at the top left so they do not overlap.
if (localStorage.getItem(STORAGE_KEY) === null) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ "kata.pinPosition": { x: START_X, y: START_Y } }));
}

void mountPin(root, new PinPositionStore(storage), { canUndo: () => false, onUndo: () => undefined }).then(() => {
  root.dataset.ready = "1";
});
