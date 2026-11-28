import { describe, expect, it } from "vitest";
import { scanBlocks } from "../src/scanner";
import { applyHighlights, clearHighlights, CLASS_KNOWN, CLASS_NEW, highlightItem, STYLE_ID } from "../src/highlight";
import type { HighlightResult } from "../src/highlight";
import type { ScanConceptItem } from "../src/coreClientTypes";

const LONG = "This paragraph has plenty of readable words in it.";
const LONG2 = "The second section also carries enough words to pass.";
const TOPIC = { id: 1, category: "ts", label: "Generics" };

function docOf(html: string): Document {
  return new DOMParser().parseFromString(html, "text/html");
}

/** Page with two scanned blocks (b0, b1); the scanner sets data-kata-block on each. */
function pageWithBlocks(): Document {
  const doc = docOf(`<h2>Alpha</h2><p>${LONG}</p><h2>Beta</h2><p>${LONG2}</p>`);
  scanBlocks(doc);
  return doc;
}

function blockEl(doc: Document, id: string): Element {
  const el = doc.querySelector(`[data-kata-block="${id}"]`);
  if (!el) throw new Error(`no block ${id}`);
  return el;
}

describe("applyHighlights", () => {
  it("adds kata-known or kata-new by the known flag", () => {
    const doc = pageWithBlocks();
    const results: HighlightResult[] = [
      { blockId: "b0", topic: TOPIC, known: true },
      { blockId: "b1", topic: TOPIC, known: false },
    ];
    applyHighlights(doc, results);
    expect(blockEl(doc, "b0").classList.contains(CLASS_KNOWN)).toBe(true);
    expect(blockEl(doc, "b0").classList.contains(CLASS_NEW)).toBe(false);
    expect(blockEl(doc, "b1").classList.contains(CLASS_NEW)).toBe(true);
    expect(blockEl(doc, "b1").classList.contains(CLASS_KNOWN)).toBe(false);
  });

  it("leaves a block with a null topic untouched", () => {
    const doc = pageWithBlocks();
    const before = blockEl(doc, "b0").outerHTML;
    applyHighlights(doc, [{ blockId: "b0", topic: null, known: null }]);
    expect(blockEl(doc, "b0").outerHTML).toBe(before);
  });

  it("never alters text content", () => {
    const doc = pageWithBlocks();
    const text = doc.body.textContent;
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true },
      { blockId: "b1", topic: TOPIC, known: false },
    ]);
    expect(doc.body.textContent).toBe(text);
  });

  it("injects one style tag when applied twice", () => {
    const doc = pageWithBlocks();
    const results: HighlightResult[] = [{ blockId: "b0", topic: TOPIC, known: true }];
    applyHighlights(doc, results);
    applyHighlights(doc, results);
    expect(doc.querySelectorAll(`style#${STYLE_ID}`)).toHaveLength(1);
    expect(blockEl(doc, "b0").classList.contains(CLASS_KNOWN)).toBe(true);
  });

  it("switches the class when a block's known flag changes", () => {
    const doc = pageWithBlocks();
    applyHighlights(doc, [{ blockId: "b0", topic: TOPIC, known: false }]);
    applyHighlights(doc, [{ blockId: "b0", topic: TOPIC, known: true }]);
    expect(blockEl(doc, "b0").classList.contains(CLASS_KNOWN)).toBe(true);
    expect(blockEl(doc, "b0").classList.contains(CLASS_NEW)).toBe(false);
  });
});

function concept(word: string, conceptId: number | null): ScanConceptItem {
  return { word, conceptId, label: word, definition: "", state: "new", candidates: [] };
}

describe("concept word spans", () => {
  it("wraps every occurrence of a concept word in a .hl span with its concept id", () => {
    const doc = docOf(`<p>${LONG} Generics help. Then generics again, Generics!</p>`);
    scanBlocks(doc);
    const text = doc.body.textContent;
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: false, concepts: [concept("Generics", 7)] },
    ]);
    const spans = blockEl(doc, "b0").querySelectorAll<HTMLElement>("span.hl");
    expect(spans).toHaveLength(2);
    expect(spans[0].textContent).toBe("Generics");
    expect(spans[0].getAttribute("data-kata-concept")).toBe("7");
    expect(highlightItem(spans[0])?.word).toBe("Generics");
    expect(doc.body.textContent).toBe(text);
  });

  it("wraps a word that occurs twice in one block", () => {
    const doc = docOf(`<p>${LONG} ${LONG}</p>`);
    scanBlocks(doc);
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true, concepts: [concept("words", 3)] },
    ]);
    expect(blockEl(doc, "b0").querySelectorAll("span.hl")).toHaveLength(2);
  });

  it("adds no span for a concept word absent from the block", () => {
    const doc = pageWithBlocks();
    const before = blockEl(doc, "b0").innerHTML;
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true, concepts: [concept("Quantum", 9)] },
    ]);
    expect(blockEl(doc, "b0").querySelectorAll("span.hl")).toHaveLength(0);
    expect(blockEl(doc, "b0").innerHTML).toBe(before);
  });

  it("does not wrap a word inside another word", () => {
    const doc = docOf(`<p>${LONG} Generics and Genericsx here</p>`);
    scanBlocks(doc);
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true, concepts: [concept("Generics", 1)] },
    ]);
    expect(blockEl(doc, "b0").querySelectorAll("span.hl")).toHaveLength(1);
  });

  it("wraps a concept word inside a link and keeps the link", () => {
    const doc = docOf(`<p>${LONG} <a href="#x">Generics</a></p>`);
    scanBlocks(doc);
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true, concepts: [concept("Generics", 2)] },
    ]);
    const links = blockEl(doc, "b0").querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("#x");
    const spans = links[0].querySelectorAll("span.hl");
    expect(spans).toHaveLength(1);
    expect(spans[0].textContent).toBe("Generics");
  });

  it("leaves a page's own span.hl untouched through apply and clear", () => {
    const doc = docOf(`<p>${LONG} <span class="hl">x</span> Generics</p>`);
    scanBlocks(doc);
    const original = doc.body.innerHTML;
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true, concepts: [concept("Generics", 1)] },
    ]);
    expect(doc.querySelectorAll("span.hl")).toHaveLength(2);
    clearHighlights(doc);
    expect(doc.body.innerHTML).toBe(original);
  });

  it("clear after apply removes every word span and restores the markup", () => {
    const doc = docOf(`<p>${LONG} Generics and <a href="#x">Generics</a> again</p>`);
    scanBlocks(doc);
    const original = doc.body.innerHTML;
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: false, concepts: [concept("Generics", 1)] },
    ]);
    expect(doc.querySelectorAll("span.hl")).toHaveLength(2);
    clearHighlights(doc);
    expect(doc.querySelectorAll("span.hl")).toHaveLength(0);
    expect(doc.body.innerHTML).toBe(original);
  });
});

describe("clearHighlights", () => {
  it("restores the DOM innerHTML exactly", () => {
    const doc = pageWithBlocks();
    const original = doc.body.innerHTML;
    const headOriginal = doc.head.innerHTML;
    applyHighlights(doc, [
      { blockId: "b0", topic: TOPIC, known: true },
      { blockId: "b1", topic: TOPIC, known: false },
    ]);
    expect(doc.body.innerHTML).not.toBe(original);
    clearHighlights(doc);
    expect(doc.body.innerHTML).toBe(original);
    expect(doc.head.innerHTML).toBe(headOriginal);
  });

  it("keeps classes that were on the element before highlighting", () => {
    const doc = docOf(`<h2 class="intro">Alpha</h2><p>${LONG}</p>`);
    scanBlocks(doc);
    applyHighlights(doc, [{ blockId: "b0", topic: TOPIC, known: true }]);
    clearHighlights(doc);
    expect(blockEl(doc, "b0").getAttribute("class")).toBe("intro");
  });
});
