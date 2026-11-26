/**
 * Floating pin position: the top-left {x, y} of the pin, saved in extension storage. When storage
 * is blocked or holds a malformed value, the position is kept in memory for this page only.
 * Positions are clamped inside the viewport on load and on resize.
 */
import type { StorageArea } from "../../tokenStore";

/** Storage key holding the pin position as one value. */
const POSITION_KEY = "kata.pinPosition";

/** Top-left corner of the pin in CSS pixels. */
export interface PinPosition {
  x: number;
  y: number;
}

/** Width and height in CSS pixels. */
export interface Size {
  width: number;
  height: number;
}

/** True when value has finite numeric x and y. */
function isPinPosition(value: unknown): value is PinPosition {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.x === "number" && Number.isFinite(v.x) && typeof v.y === "number" && Number.isFinite(v.y);
}

/** Keeps the pin position in extension storage, with a memory copy as fallback. */
export class PinPositionStore {
  private memory: PinPosition | null = null;

  constructor(private readonly area: StorageArea) {}

  /** Returns the stored position, else the memory copy; null when neither exists. */
  async load(): Promise<PinPosition | null> {
    try {
      const items = await this.area.get(POSITION_KEY);
      const value = items[POSITION_KEY];
      if (isPinPosition(value)) return { x: value.x, y: value.y };
    } catch {
      // Storage blocked: the memory copy below answers.
    }
    return this.memory;
  }

  /** Writes the position to storage and to memory. Storage errors leave the memory copy in place. */
  async save(position: PinPosition): Promise<void> {
    this.memory = { x: position.x, y: position.y };
    try {
      await this.area.set({ [POSITION_KEY]: { x: position.x, y: position.y } });
    } catch {
      // Storage blocked: the position stays in memory for this page.
    }
  }
}

/**
 * Moves position so a pin of size pin stays inside viewport. A pin larger than the viewport sits
 * at 0 on that axis.
 */
export function clampPinPosition(position: PinPosition, viewport: Size, pin: Size): PinPosition {
  const maxX = Math.max(0, viewport.width - pin.width);
  const maxY = Math.max(0, viewport.height - pin.height);
  return {
    x: Math.min(Math.max(position.x, 0), maxX),
    y: Math.min(Math.max(position.y, 0), maxY),
  };
}
