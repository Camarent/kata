/**
 * Floating pin: the mascot button opens a mini-menu with one Undo. The pin drags to a stored
 * spot, collapses to a small icon button and expands again. Esc closes the menu (via popover).
 * Screens: "pin" when expanded, "pin-collapsed" when collapsed.
 */
import { el } from "../dom";
import { createPopover } from "../popover";
import { TEXT_PIN, TEXT_PIN_COLLAPSED } from "../strings";
import { type PinPosition, type PinPositionStore, clampPinPosition } from "./pinPosition";

const [MASCOT_LABEL, , COLLAPSE_LABEL, , , , UNDO_LABEL, NOTHING_TO_UNDO_LABEL] = TEXT_PIN;
const [OPEN_COLLAPSED_LABEL] = TEXT_PIN_COLLAPSED;
/** Drag grip glyph; decorative, so it carries no label. */
const GRIP_GLYPH = "⋮";
/** Collapse glyph; the label is on the button as aria-label and title. */
const COLLAPSE_GLYPH = "−";

/** Undo state and action the mini-menu calls. */
export interface PinActions {
  canUndo(): boolean;
  onUndo(): void;
}

export interface Pin {
  /** Root element of the pin; attached to the parent given to mountPin. */
  readonly element: HTMLElement;
  readonly collapsed: boolean;
  /** True while the mini-menu is open. */
  readonly menuOpen: boolean;
  /** Shows the small icon button; an open mini-menu closes with it. No-op when already collapsed. */
  collapse(): void;
  /** Shows the full pin again. No-op when already expanded. */
  expand(): void;
  /** Closes the menu, removes the resize listener and the element. */
  dispose(): void;
}

/** Places the pin in parent at its stored position (clamped), then returns it ready to use. */
export async function mountPin(parent: HTMLElement, store: PinPositionStore, actions: PinActions): Promise<Pin> {
  const root = el("div", undefined, "float");
  const expanded = el("div", undefined, "pinwrap");

  const grip = el("span", GRIP_GLYPH, "drag");
  grip.setAttribute("aria-hidden", "true");

  const mascot = el("button", undefined, "pinbtn");
  mascot.type = "button";
  mascot.title = MASCOT_LABEL;
  mascot.setAttribute("aria-label", MASCOT_LABEL);
  mascot.setAttribute("aria-haspopup", "menu");

  const collapse = el("button", COLLAPSE_GLYPH, "x");
  collapse.type = "button";
  collapse.title = COLLAPSE_LABEL;
  collapse.setAttribute("aria-label", COLLAPSE_LABEL);

  expanded.append(grip, mascot, collapse);

  const undo = el("button", UNDO_LABEL, "menu-undo");
  undo.type = "button";
  const menu = el("div", undefined, "pin-menu");
  menu.setAttribute("role", "menu");
  menu.append(undo);
  const popover = createPopover(mascot, menu);

  const refreshUndo = (): void => {
    const can = actions.canUndo();
    undo.disabled = !can;
    undo.title = can ? UNDO_LABEL : NOTHING_TO_UNDO_LABEL;
  };
  mascot.addEventListener("click", () => {
    if (popover.isOpen) {
      popover.close();
      return;
    }
    refreshUndo();
    popover.open();
  });
  undo.addEventListener("click", () => {
    popover.close();
    actions.onUndo();
  });

  const collapsedBtn = el("button", undefined, "pinbtn");
  collapsedBtn.type = "button";
  collapsedBtn.title = OPEN_COLLAPSED_LABEL;
  collapsedBtn.setAttribute("aria-label", OPEN_COLLAPSED_LABEL);

  root.append(expanded, popover.element, collapsedBtn);
  parent.append(root);

  let collapsed = false;
  const applyView = (): void => {
    expanded.hidden = collapsed;
    collapsedBtn.hidden = !collapsed;
    root.dataset.screen = collapsed ? "pin-collapsed" : "pin";
  };

  // Current position, in CSS pixels; null until one is stored or dragged.
  let position: PinPosition | null = null;
  const place = (x: number, y: number): void => {
    const size = { width: root.offsetWidth, height: root.offsetHeight };
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    position = clampPinPosition({ x, y }, viewport, size);
    root.style.left = `${position.x}px`;
    root.style.top = `${position.y}px`;
    root.style.right = "auto";
    root.style.bottom = "auto";
  };
  const onResize = (): void => {
    if (position) place(position.x, position.y);
  };
  window.addEventListener("resize", onResize);

  // Drag: grab offset is set on pointerdown; the position is saved once, on pointerup.
  let grab: { dx: number; dy: number } | null = null;
  const onMove = (event: MouseEvent): void => {
    if (grab) place(event.clientX - grab.dx, event.clientY - grab.dy);
  };
  const onUp = (): void => {
    if (!grab) return;
    grab = null;
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    if (position) void store.save(position);
  };
  grip.addEventListener("pointerdown", (event: PointerEvent) => {
    const rect = root.getBoundingClientRect();
    grab = { dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });

  const stored = await store.load();
  if (stored) place(stored.x, stored.y);

  const pin: Pin = {
    element: root,
    get collapsed() {
      return collapsed;
    },
    get menuOpen() {
      return popover.isOpen;
    },
    collapse(): void {
      if (collapsed) return;
      popover.close();
      collapsed = true;
      applyView();
    },
    expand(): void {
      if (!collapsed) return;
      collapsed = false;
      applyView();
    },
    dispose(): void {
      popover.close();
      window.removeEventListener("resize", onResize);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      root.remove();
    },
  };
  collapse.addEventListener("click", () => pin.collapse());
  collapsedBtn.addEventListener("click", () => pin.expand());

  applyView();
  refreshUndo();
  return pin;
}
