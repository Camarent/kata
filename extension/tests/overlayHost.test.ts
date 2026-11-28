import { afterEach, describe, expect, it, vi } from "vitest";
import { applyHighlights, clearHighlights, type HighlightResult } from "../src/highlight";
import { attachImageMenus, createOverlayHost } from "../src/overlayHost";
import type { RuntimeLike } from "../src/messages";
import type { ScanConceptItem } from "../src/coreClientTypes";
import { BLOCK_ATTR } from "../src/scanner";
import { TEXT_IMAGE_PIN_MENU } from "../src/ui/strings";

const MENU = ".hl-hover-menu";
const IMAGE_PIN = ".image-pin";
const IMAGE_MENU = ".image-pin-menu";

function item(over: Partial<ScanConceptItem> = {}): ScanConceptItem {
  return {
    word: "SYN",
    conceptId: 7,
    label: "SYN",
    definition: "first step of the TCP handshake",
    state: "new",
    candidates: [],
    ...over,
  };
}

/** One page block with the word SYN, highlighted as concept 7 of topic 3. */
function pageWithHighlight(): HTMLElement {
  document.body.innerHTML = `<p ${BLOCK_ATTR}="b1">SYN then ACK</p>`;
  const block = document.querySelector<HTMLElement>(`[${BLOCK_ATTR}="b1"]`);
  if (!block) throw new Error("block missing");
  applyHighlights(document, [
    { blockId: "b1", topic: { id: 3, category: "net", label: "tcp" }, known: false, concepts: [item()] },
  ]);
  return block;
}

/** The highlight result of block b1 (topic 3) with `concepts`; default is one new concept. */
function sectionResult(concepts: ScanConceptItem[] = [item()]): HighlightResult {
  return { blockId: "b1", topic: { id: 3, category: "net", label: "tcp" }, known: false, concepts };
}

function runtimeFake(): RuntimeLike & { sendMessage: ReturnType<typeof vi.fn> } {
  return {
    onMessage: { addListener: vi.fn() },
    sendMessage: vi.fn(async () => ({ ok: true })),
  };
}

/** Detach of the image menus a test attached; afterEach runs it so no observer outlives the test. */
let detachImages: (() => void) | undefined;

afterEach(() => {
  detachImages?.();
  detachImages = undefined;
  clearHighlights(document);
  document.body.innerHTML = "";
});

describe("overlay host", () => {
  it("shows the section quiz pin for new concepts and sends the mini quiz request on its action", () => {
    const runtime = runtimeFake();
    const overlay = createOverlayHost(runtime);
    pageWithHighlight();
    overlay.attach(document, [sectionResult()]);
    const start = document.querySelector<HTMLButtonElement>(".quiz-pin button");
    expect(start?.disabled).toBe(false);
    start?.click();
    expect(runtime.sendMessage).toHaveBeenCalledWith({ type: "panel:miniQuiz" });
    overlay.clear();
    expect(document.querySelector(".quiz-pin")).toBeNull();
  });

  it("hides the section quiz pin in focus mode", () => {
    const overlay = createOverlayHost(runtimeFake(), () => ({ focusOn: true, offline: false }));
    pageWithHighlight();
    overlay.attach(document, [sectionResult()]);
    expect(document.querySelector(".quiz-pin")).toBeNull();
    overlay.clear();
  });

  it("disables the section quiz pin's action while the core is offline", () => {
    const overlay = createOverlayHost(runtimeFake(), () => ({ focusOn: false, offline: true }));
    pageWithHighlight();
    overlay.attach(document, [sectionResult()]);
    expect(document.querySelector<HTMLButtonElement>(".quiz-pin button")?.disabled).toBe(true);
    overlay.clear();
  });

  it("shows no section quiz pin when the section has no new concepts", () => {
    const overlay = createOverlayHost(runtimeFake());
    pageWithHighlight();
    overlay.attach(document, [sectionResult([item({ state: "known" })])]);
    expect(document.querySelector(".quiz-pin")).toBeNull();
    overlay.clear();
  });

  it("attaches one hover menu per highlighted word and removes it on clear", () => {
    const runtime = runtimeFake();
    const overlay = createOverlayHost(runtime);
    pageWithHighlight();
    overlay.attach(document, [{ blockId: "b1", topic: { id: 3, category: "net", label: "tcp" }, known: false, concepts: [item()] }]);
    expect(document.querySelectorAll(MENU)).toHaveLength(1);
    expect(document.querySelector(MENU)?.textContent).toContain("SYN");
    overlay.clear();
    expect(document.querySelectorAll(MENU)).toHaveLength(0);
  });

  it("does not stack menus when attached twice", () => {
    const overlay = createOverlayHost(runtimeFake());
    pageWithHighlight();
    const results = [{ blockId: "b1", topic: { id: 3, category: "net", label: "tcp" }, known: false, concepts: [item()] }];
    overlay.attach(document, results);
    overlay.attach(document, results);
    expect(document.querySelectorAll(MENU)).toHaveLength(1);
  });

  it("sends the state button press to the background as a panel message", async () => {
    const runtime = runtimeFake();
    const overlay = createOverlayHost(runtime);
    pageWithHighlight();
    overlay.attach(document, [{ blockId: "b1", topic: { id: 3, category: "net", label: "tcp" }, known: false, concepts: [item()] }]);
    const button = document.querySelector<HTMLButtonElement>(`${MENU} button`);
    if (!button) throw new Error("no state button");
    button.click();
    await vi.waitFor(() => expect(runtime.sendMessage).toHaveBeenCalled());
    expect(runtime.sendMessage.mock.calls[0]?.[0]).toMatchObject({ type: "panel:setConcept", conceptId: 7 });
  });

  it("opens the image menu when its pin is hovered, and sends the picked action as a panel message", async () => {
    const runtime = runtimeFake();
    document.body.innerHTML = `<img id="pic" alt="diagram" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">`;
    const img = document.querySelector<HTMLImageElement>("#pic");
    if (!img) throw new Error("image missing");
    detachImages = attachImageMenus(document, runtime);
    img.dispatchEvent(new MouseEvent("mouseenter"));
    const pin = document.querySelector<HTMLButtonElement>(IMAGE_PIN);
    if (!pin) throw new Error("no image pin");
    expect(document.querySelector(IMAGE_MENU)).toBeNull();
    pin.dispatchEvent(new MouseEvent("mouseenter"));
    expect(document.querySelector(IMAGE_MENU)).not.toBeNull();
    const action = document.querySelector<HTMLButtonElement>(`${IMAGE_MENU} .btn`);
    action?.click();
    await vi.waitFor(() => expect(runtime.sendMessage).toHaveBeenCalled());
    expect(runtime.sendMessage.mock.calls[0]?.[0]).toEqual({ type: "panel:imageAction", label: TEXT_IMAGE_PIN_MENU[0] });
  });

  it("gives the image menu to an image added after the attach", async () => {
    detachImages = attachImageMenus(document, runtimeFake());
    document.body.insertAdjacentHTML("beforeend", `<img id="late" alt="late" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">`);
    const img = document.querySelector<HTMLImageElement>("#late");
    if (!img) throw new Error("late image missing");
    // The observer attaches on a microtask, so the hover is retried until the pin listens to it.
    await vi.waitFor(() => {
      img.dispatchEvent(new MouseEvent("mouseenter"));
      expect(document.querySelector(IMAGE_PIN)).not.toBeNull();
    });
  });

  it("removes the image pins and menus with its detach", () => {
    document.body.innerHTML = `<img id="pic" alt="diagram" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">`;
    const img = document.querySelector<HTMLImageElement>("#pic");
    if (!img) throw new Error("image missing");
    const detach = attachImageMenus(document, runtimeFake());
    img.dispatchEvent(new MouseEvent("mouseenter"));
    expect(document.querySelector(IMAGE_PIN)).not.toBeNull();
    detach();
    expect(document.querySelector(IMAGE_PIN)).toBeNull();
  });
});
