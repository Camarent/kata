import { el } from "./dom";

export interface Popover {
  /** The popover box; the caller places it in the page. Starts hidden. */
  readonly element: HTMLElement;
  readonly isOpen: boolean;
  open(): void;
  /** Hides the box and removes the document listeners. Safe to call when already closed. */
  close(): void;
}

/**
 * Popover with content. It opens with open() and closes on Escape or on a mousedown/click outside
 * both the popover and its anchor. Document listeners exist only while it is open.
 */
export function createPopover(anchor: HTMLElement, content: HTMLElement): Popover {
  const element = el("div", undefined, "popover");
  element.hidden = true;
  element.append(content);
  let isOpen = false;

  const onKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") popover.close();
  };
  const onOutside = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (element.contains(target) || anchor.contains(target)) return;
    popover.close();
  };

  const popover: Popover = {
    element,
    get isOpen() {
      return isOpen;
    },
    open(): void {
      if (isOpen) return;
      isOpen = true;
      element.hidden = false;
      document.addEventListener("keydown", onKeydown);
      document.addEventListener("mousedown", onOutside, true);
      document.addEventListener("click", onOutside, true);
    },
    close(): void {
      if (!isOpen) return;
      isOpen = false;
      element.hidden = true;
      document.removeEventListener("keydown", onKeydown);
      document.removeEventListener("mousedown", onOutside, true);
      document.removeEventListener("click", onOutside, true);
    },
  };
  return popover;
}
