import { BLOCK_ATTR } from "./scanner";
import type { JobStatus } from "./coreClient";
import type { ScanConceptItem } from "./coreClientTypes";

/** Result of one scanned block: the block id, the job answer for it, and the concepts found in it. */
export interface HighlightResult {
  blockId: string;
  topic: JobStatus["topic"];
  known: boolean | null;
  concepts?: ScanConceptItem[];
}

/** Class put on a block whose topic the user already knows. */
export const CLASS_KNOWN = "kata-known";
/** Class put on a block whose topic is new to the user. */
export const CLASS_NEW = "kata-new";
/** Id of the single style tag injected by applyHighlights. */
export const STYLE_ID = "kata-highlight-style";
/** Class of the word span wrapped around each concept word in a block. */
export const CLASS_HL = "hl";
/** Attribute on a word span holding its concept id; absent when the concept is null. */
export const ATTR_CONCEPT = "data-kata-concept";
/** Marker attribute on every word span this module creates; unwrap touches only marked spans. */
export const ATTR_HL = "data-kata-hl";

const STYLE_TEXT = `
.${CLASS_KNOWN} { background-color: #e6f4ea; }
.${CLASS_NEW} { background-color: #fff4d6; }
`;

/** Scan item behind each word span, keyed by the span element. */
const spanItems = new WeakMap<HTMLElement, ScanConceptItem>();

/** The scan item a `.hl` word span stands for, or undefined for any other element. */
export function highlightItem(span: HTMLElement): ScanConceptItem | undefined {
  return spanItems.get(span);
}

/** Add the highlight style tag once. Repeated calls find it and do nothing. */
function ensureStyle(doc: Document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = STYLE_TEXT;
  (doc.head ?? doc.documentElement).appendChild(style);
}

/** Block elements of the page, keyed by their `data-kata-block` id. */
function blocksById(doc: Document): Map<string, HTMLElement> {
  const map = new Map<string, HTMLElement>();
  for (const el of Array.from(doc.querySelectorAll<HTMLElement>(`[${BLOCK_ATTR}]`))) {
    const id = el.getAttribute(BLOCK_ATTR);
    if (id !== null) map.set(id, el);
  }
  return map;
}

/** Replace every word span this module made under `scope` by its text, merging the text back together. */
function unwrapWords(scope: ParentNode): void {
  for (const span of Array.from(scope.querySelectorAll<HTMLElement>(`span[${ATTR_HL}]`))) {
    const parent = span.parentNode;
    if (!parent) continue;
    span.replaceWith(...Array.from(span.childNodes));
    parent.normalize();
  }
}

/** Text nodes under `root`, in document order. */
function textNodesOf(root: HTMLElement): Text[] {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text);
  return nodes;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Wrap each occurrence of a concept word in the block text in a `.hl` span. Words match whole
 * (no letter or digit next to them), longest first. Text nodes are split, never copied, so the
 * text content is unchanged. A word absent from the block adds nothing.
 */
function wrapWords(block: HTMLElement, concepts: ScanConceptItem[]): void {
  const byWord = new Map<string, ScanConceptItem>();
  for (const item of concepts) {
    if (item.word !== "" && !byWord.has(item.word)) byWord.set(item.word, item);
  }
  if (byWord.size === 0) return;
  const words = [...byWord.keys()].sort((a, b) => b.length - a.length).map(escapeRegExp);
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}])(?:${words.join("|")})(?![\\p{L}\\p{N}])`, "gu");
  const doc = block.ownerDocument;

  for (const node of textNodesOf(block)) {
    const text = node.data;
    const matches = Array.from(text.matchAll(pattern));
    if (matches.length === 0) continue;
    const fragment = doc.createDocumentFragment();
    let last = 0;
    for (const match of matches) {
      const start = match.index ?? 0;
      const word = match[0];
      const item = byWord.get(word);
      if (!item) continue;
      const span = doc.createElement("span");
      span.className = CLASS_HL;
      span.setAttribute(ATTR_HL, "");
      if (item.conceptId !== null) span.setAttribute(ATTR_CONCEPT, String(item.conceptId));
      span.textContent = word;
      spanItems.set(span, item);
      fragment.append(text.slice(last, start), span);
      last = start + word.length;
    }
    fragment.append(text.slice(last));
    node.replaceWith(fragment);
  }
}

/**
 * Mark each block with a topic: `kata-known` when the user knows the topic,
 * `kata-new` when not. Results without a topic, or with a null `known`, leave
 * the block alone. Concept words of a marked block are wrapped in `.hl` spans.
 * Only classes and word spans change; text content is never altered.
 */
export function applyHighlights(doc: Document, results: HighlightResult[]): void {
  const blocks = blocksById(doc);
  ensureStyle(doc);
  for (const result of results) {
    if (result.topic === null || result.known === null) continue;
    const el = blocks.get(result.blockId);
    if (!el) continue;
    el.classList.remove(CLASS_KNOWN, CLASS_NEW);
    el.classList.add(result.known ? CLASS_KNOWN : CLASS_NEW);
    unwrapWords(el);
    wrapWords(el, result.concepts ?? []);
  }
}

/** Remove the word spans, the highlight classes and the style tag, restoring the page markup. */
export function clearHighlights(doc: Document): void {
  unwrapWords(doc);
  for (const el of Array.from(doc.querySelectorAll<HTMLElement>(`[${BLOCK_ATTR}]`))) {
    el.classList.remove(CLASS_KNOWN, CLASS_NEW);
    // classList.remove leaves an empty class attribute behind; drop it so the markup matches the original.
    if (el.classList.length === 0) el.removeAttribute("class");
  }
  doc.getElementById(STYLE_ID)?.remove();
}
