import type { Block } from "./types";

/** Blocks shorter than this many characters are dropped. */
export const DEFAULT_MIN_CHARS = 20;
/** Block text is truncated to this many characters. */
const DEFAULT_MAX_CHARS = 2000;

/** Attribute set on each emitted block element; highlight.ts reads it. */
export const BLOCK_ATTR = "data-kata-block";

const HEADING_SELECTOR = "h1, h2, h3";
const TEXT_SELECTOR = "p, li, blockquote, pre, td, th, dd, figcaption";
const SKIPPED_TAGS = ["script", "style", "nav"];

export interface ScanOptions {
  minChars?: number;
  maxChars?: number;
}

/** Heading or text element plus the text collected under it. */
interface Group {
  el: HTMLElement;
  parts: string[];
}

/** True when the element itself is skipped (not its ancestors). */
function isSkippedNode(el: Element): boolean {
  return (
    SKIPPED_TAGS.includes(el.localName) ||
    el.hasAttribute("hidden") ||
    (el as HTMLElement).style?.display === "none"
  );
}

/** True when the element or any ancestor is skipped. */
function isInSkipped(el: Element): boolean {
  for (let cur: Element | null = el; cur; cur = cur.parentElement) {
    if (isSkippedNode(cur)) return true;
  }
  return false;
}

/** Text of a node, leaving out skipped descendants (script, style, hidden...). */
function textOf(node: Node): string {
  let out = "";
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      out += child.textContent ?? "";
    } else if (child.nodeType === Node.ELEMENT_NODE && !isSkippedNode(child as Element)) {
      out += textOf(child);
    }
  }
  return out;
}

function clean(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Walk the body in document order. Each heading opens a group that takes the
 * text units after it. Text units before any heading (or on a page without
 * headings) become one group each.
 */
function collectGroups(doc: Document): Group[] {
  const root = doc.body;
  if (!root) return [];
  const groups: Group[] = [];
  let open: Group | null = null;
  const nodes = root.querySelectorAll<HTMLElement>(`${HEADING_SELECTOR}, ${TEXT_SELECTOR}`);
  for (const el of Array.from(nodes)) {
    if (isInSkipped(el)) continue;
    if (el.matches(HEADING_SELECTOR)) {
      open = { el, parts: [textOf(el)] };
      groups.push(open);
      continue;
    }
    // A unit holding a smaller unit (li > p) is skipped: the inner one is scanned.
    if (el.querySelector(TEXT_SELECTOR)) continue;
    const text = textOf(el);
    if (!text) continue;
    if (open) {
      open.parts.push(text);
    } else {
      groups.push({ el, parts: [text] });
    }
  }
  return groups;
}

/**
 * Split a page into readable blocks. Ids are `b<index>` over all groups in
 * document order, so an id does not move when a short group is dropped.
 * Each emitted block element gets `data-kata-block=<id>`.
 */
export function scanBlocks(doc: Document, opts: ScanOptions = {}): Block[] {
  const minChars = opts.minChars ?? DEFAULT_MIN_CHARS;
  const maxChars = opts.maxChars ?? DEFAULT_MAX_CHARS;
  const blocks: Block[] = [];
  collectGroups(doc).forEach((group, index) => {
    const text = clean(group.parts.join(" "));
    if (text.length < minChars) return;
    const id = `b${index}`;
    group.el.setAttribute(BLOCK_ATTR, id);
    blocks.push({ id, text: text.slice(0, maxChars), el: group.el });
  });
  return blocks;
}
