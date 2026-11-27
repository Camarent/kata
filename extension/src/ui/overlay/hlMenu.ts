import type { CoreClient } from "../../coreClient";
import type { ScanConceptItem } from "../../coreClientTypes";
import type { ReviewState } from "../../types";
import { el } from "../dom";
import { createPopover } from "../popover";
import { renderStateMenu } from "../stateMenu";
import { HL_HOVER_MENU_TEXT } from "../strings";
import { renderWhichOne } from "./whichOne";

export interface HlMenuOptions {
  topicId: number;
  /** The word as written on the page. */
  word: string;
  item: ScanConceptItem;
  offline: boolean;
  client: Pick<CoreClient, "chooseConcept" | "reassignConcept">;
  /** Sets the concept state chosen with the New / Learning / Known buttons. */
  onState: (state: ReviewState) => void | Promise<void>;
}

/**
 * Concept menu body: concept name, definition line, New / Learning / Known buttons and
 * "Not this meaning". `showPanel` swaps the body to another panel (the "Which one?" list).
 */
export function renderHlMenu(opts: HlMenuOptions, showPanel: (content: HTMLElement) => void): HTMLElement {
  const { item } = opts;
  let current = item.conceptId;
  const root = el("div", undefined, "hl-hover-menu");
  root.append(el("h2", item.label, "concept"));
  if (item.definition !== "") root.append(el("p", item.definition, "definition"));
  root.append(renderStateMenu(item.state, opts.onState));
  if (opts.offline) root.append(el("p", HL_HOVER_MENU_TEXT.offline, "offline"));

  if (item.candidates.length === 0) {
    root.append(el("p", HL_HOVER_MENU_TEXT.noMeaning, "no-meaning"));
  } else {
    const notThis = el("button", HL_HOVER_MENU_TEXT.notThisMeaning, "not-this-meaning");
    notThis.type = "button";
    notThis.addEventListener("click", () => {
      showPanel(
        renderWhichOne({
          topicId: opts.topicId,
          word: opts.word,
          candidates: item.candidates,
          client: opts.client,
          onPick: async (candidate) => {
            // Move this highlight only when it has a concept now and the pick is another one.
            if (current === null || current === candidate.conceptId) return;
            await opts.client.reassignConcept(opts.topicId, opts.word, current, candidate.conceptId);
            // A later pick in the same menu moves from this concept, not the original one.
            current = candidate.conceptId;
          },
        }),
      );
    });
    root.append(notThis);
  }
  return root;
}

/**
 * Hover menu for one highlighted word. Hover or focus on `host` opens an absolutely positioned
 * popover at the host's box; the host's own markup and style are never touched, so no layout shifts.
 * Returns a cleanup that removes every listener and the popover.
 */
export function attachHlHover(host: HTMLElement, opts: HlMenuOptions): () => void {
  const doc = host.ownerDocument;
  const menu = renderHlMenu(opts, (content) => popover.element.replaceChildren(content));
  const popover = createPopover(host, menu);
  doc.body.append(popover.element);

  const openAt = (): void => {
    const rect = host.getBoundingClientRect();
    const win = doc.defaultView;
    popover.element.style.position = "absolute";
    popover.element.style.top = `${rect.bottom + (win?.scrollY ?? 0)}px`;
    popover.element.style.left = `${rect.left + (win?.scrollX ?? 0)}px`;
    popover.open();
  };
  // Moving the pointer from the word into the menu keeps it open.
  const leave = (event: MouseEvent, other: HTMLElement): void => {
    const next = event.relatedTarget;
    if (next instanceof Node && other.contains(next)) return;
    popover.close();
  };
  const onHostLeave = (event: MouseEvent): void => leave(event, popover.element);
  const onMenuLeave = (event: MouseEvent): void => leave(event, host);

  host.addEventListener("mouseenter", openAt);
  host.addEventListener("focus", openAt);
  host.addEventListener("mouseleave", onHostLeave);
  popover.element.addEventListener("mouseleave", onMenuLeave);
  // Tabbing away closes the menu unless focus moves between the word and the menu.
  const onFocusOut = (event: FocusEvent): void => {
    const next = event.relatedTarget;
    if (next instanceof Node && (host.contains(next) || popover.element.contains(next))) return;
    popover.close();
  };
  host.addEventListener("focusout", onFocusOut);
  popover.element.addEventListener("focusout", onFocusOut);

  return () => {
    host.removeEventListener("focusout", onFocusOut);
    popover.element.removeEventListener("focusout", onFocusOut);
    host.removeEventListener("mouseenter", openAt);
    host.removeEventListener("focus", openAt);
    host.removeEventListener("mouseleave", onHostLeave);
    popover.element.removeEventListener("mouseleave", onMenuLeave);
    popover.close();
    popover.element.remove();
  };
}
