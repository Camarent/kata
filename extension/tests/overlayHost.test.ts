import { afterEach, describe, expect, it, vi } from "vitest";
import { applyHighlights, clearHighlights } from "../src/highlight";
import { createOverlayHost } from "../src/overlayHost";
import type { RuntimeLike } from "../src/messages";
import type { ScanConceptItem } from "../src/coreClientTypes";
import { BLOCK_ATTR } from "../src/scanner";

const MENU = ".hl-hover-menu";

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

function runtimeFake(): RuntimeLike & { sendMessage: ReturnType<typeof vi.fn> } {
  return {
    onMessage: { addListener: vi.fn() },
    sendMessage: vi.fn(async () => ({ ok: true })),
  };
}

afterEach(() => {
  clearHighlights(document);
  document.body.innerHTML = "";
});

describe("overlay host", () => {
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
});
