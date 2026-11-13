import { BLOCK_ATTR } from "./scanner";
import type { JobStatus } from "./coreClient";

/** Result of one scanned block: the block id and the job answer for it. */
export interface HighlightResult {
  blockId: string;
  topic: JobStatus["topic"];
  known: boolean | null;
}

/** Class put on a block whose topic the user already knows. */
export const CLASS_KNOWN = "kata-known";
/** Class put on a block whose topic is new to the user. */
export const CLASS_NEW = "kata-new";
/** Id of the single style tag injected by applyHighlights. */
export const STYLE_ID = "kata-highlight-style";

const STYLE_TEXT = `
.${CLASS_KNOWN} { background-color: #e6f4ea; }
.${CLASS_NEW} { background-color: #fff4d6; }
`;

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

/**
 * Mark each block with a topic: `kata-known` when the user knows the topic,
 * `kata-new` when not. Results without a topic, or with a null `known`, leave
 * the block alone. Only classes change; text content is never altered.
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
  }
}

/** Remove the highlight classes and the style tag, restoring the page markup. */
export function clearHighlights(doc: Document): void {
  for (const el of Array.from(doc.querySelectorAll<HTMLElement>(`[${BLOCK_ATTR}]`))) {
    el.classList.remove(CLASS_KNOWN, CLASS_NEW);
    // classList.remove leaves an empty class attribute behind; drop it so the markup matches the original.
    if (el.classList.length === 0) el.removeAttribute("class");
  }
  doc.getElementById(STYLE_ID)?.remove();
}
