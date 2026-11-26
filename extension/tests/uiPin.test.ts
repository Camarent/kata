import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type Pin, mountPin } from "../src/ui/card/pin";
import { PinPositionStore, clampPinPosition } from "../src/ui/card/pinPosition";
import type { StorageArea } from "../src/tokenStore";

const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

/** In-memory chrome.storage.local stand-in; `fail` makes every call reject. */
function fakeArea(fail = false): StorageArea & { data: Record<string, unknown> } {
  const data: Record<string, unknown> = {};
  const guard = (): void => {
    if (fail) throw new Error("storage blocked");
  };
  return {
    data,
    async get(key) {
      guard();
      return key in data ? { [key]: data[key] } : {};
    },
    async set(items) {
      guard();
      Object.assign(data, items);
    },
    async remove(key) {
      guard();
      delete data[key];
    },
  };
}

function setViewport(width: number, height: number): void {
  window.innerWidth = width;
  window.innerHeight = height;
}

function pointer(type: string, clientX: number, clientY: number): void {
  document.dispatchEvent(new MouseEvent(type, { clientX, clientY, bubbles: true }));
}

describe("clampPinPosition", () => {
  const pin = { width: 100, height: 50 };

  it("keeps an inside position unchanged", () => {
    expect(clampPinPosition({ x: 10, y: 20 }, { width: 400, height: 300 }, pin)).toEqual({ x: 10, y: 20 });
  });

  it("pulls a position past the right and bottom edge back inside", () => {
    expect(clampPinPosition({ x: 900, y: 700 }, { width: 400, height: 300 }, pin)).toEqual({ x: 300, y: 250 });
  });

  it("moves a negative position to the origin", () => {
    expect(clampPinPosition({ x: -5, y: -9 }, { width: 400, height: 300 }, pin)).toEqual({ x: 0, y: 0 });
  });

  it("sits at 0 when the pin is larger than the viewport", () => {
    expect(clampPinPosition({ x: 30, y: 30 }, { width: 80, height: 20 }, pin)).toEqual({ x: 0, y: 0 });
  });
});

describe("PinPositionStore", () => {
  it("saves {x, y} under extension storage and loads it back", async () => {
    const area = fakeArea();
    await new PinPositionStore(area).save({ x: 12, y: 34 });
    expect(area.data["kata.pinPosition"]).toEqual({ x: 12, y: 34 });
    expect(await new PinPositionStore(area).load()).toEqual({ x: 12, y: 34 });
  });

  it("loads null when nothing is stored", async () => {
    expect(await new PinPositionStore(fakeArea()).load()).toBeNull();
  });

  it("ignores a malformed stored value", async () => {
    const area = fakeArea();
    area.data["kata.pinPosition"] = { x: "left", y: 3 };
    expect(await new PinPositionStore(area).load()).toBeNull();
  });

  it("keeps the position in memory when storage is blocked", async () => {
    const store = new PinPositionStore(fakeArea(true));
    await store.save({ x: 7, y: 8 });
    expect(await store.load()).toEqual({ x: 7, y: 8 });
  });
});

describe("mountPin", () => {
  let parent: HTMLElement;
  let pins: Pin[];
  let savedWidth: number;
  let savedHeight: number;

  beforeEach(() => {
    savedWidth = window.innerWidth;
    savedHeight = window.innerHeight;
    setViewport(400, 300);
    parent = document.createElement("div");
    document.body.append(parent);
    pins = [];
  });

  afterEach(() => {
    for (const pin of pins) pin.dispose();
    parent.remove();
    setViewport(savedWidth, savedHeight);
  });

  const mount = async (store: PinPositionStore, canUndo = true) => {
    const calls = { undo: 0 };
    const pin = await mountPin(parent, store, {
      canUndo: () => canUndo,
      onUndo: () => {
        calls.undo += 1;
      },
    });
    pins.push(pin);
    return { pin, calls };
  };

  it("drags to a new spot, clamps it and saves it once on release", async () => {
    const area = fakeArea();
    const store = new PinPositionStore(area);
    const { pin } = await mount(store);
    const grip = pin.element.querySelector<HTMLElement>(".drag");
    grip?.dispatchEvent(new MouseEvent("pointerdown", { clientX: 0, clientY: 0, bubbles: true }));
    pointer("pointermove", 50, 40);
    pointer("pointermove", 5000, 5000);
    expect(pin.element.style.left).toBe("400px");
    expect(pin.element.style.top).toBe("300px");
    expect(area.data["kata.pinPosition"]).toBeUndefined();
    pointer("pointerup", 5000, 5000);
    expect(area.data["kata.pinPosition"]).toEqual({ x: 400, y: 300 });
    pointer("pointermove", 1, 1);
    expect(pin.element.style.left).toBe("400px");
  });

  it("restores a stored position clamped to a smaller viewport", async () => {
    const area = fakeArea();
    area.data["kata.pinPosition"] = { x: 350, y: 250 };
    setViewport(200, 200);
    const { pin } = await mount(new PinPositionStore(area));
    expect(pin.element.style.left).toBe("200px");
    expect(pin.element.style.top).toBe("200px");
  });

  it("reclamps on window resize without saving", async () => {
    const area = fakeArea();
    area.data["kata.pinPosition"] = { x: 350, y: 250 };
    const { pin } = await mount(new PinPositionStore(area));
    setViewport(100, 100);
    window.dispatchEvent(new Event("resize"));
    expect(pin.element.style.left).toBe("100px");
    expect(area.data["kata.pinPosition"]).toEqual({ x: 350, y: 250 });
  });

  it("collapses to the icon screen and expands again", async () => {
    const { pin } = await mount(new PinPositionStore(fakeArea()));
    expect(pin.element.dataset.screen).toBe("pin");
    pin.element.querySelector<HTMLButtonElement>('button[aria-label="Collapse pin"]')?.click();
    expect(pin.collapsed).toBe(true);
    expect(pin.element.dataset.screen).toBe("pin-collapsed");
    const open = pin.element.querySelector<HTMLButtonElement>('button[aria-label="Open pin"]');
    expect(open?.hidden).toBe(false);
    open?.click();
    expect(pin.collapsed).toBe(false);
    expect(pin.element.dataset.screen).toBe("pin");
  });

  it("closes an open mini-menu when the pin collapses", async () => {
    const { pin } = await mount(new PinPositionStore(fakeArea()));
    pin.element.querySelector<HTMLButtonElement>('button[aria-label="kata"]')?.click();
    expect(pin.menuOpen).toBe(true);
    pin.collapse();
    expect(pin.menuOpen).toBe(false);
  });

  it("shows one Undo in the mini-menu and calls onUndo once", async () => {
    const { pin, calls } = await mount(new PinPositionStore(fakeArea()));
    pin.element.querySelector<HTMLButtonElement>('button[aria-label="kata"]')?.click();
    const buttons = pin.element.querySelectorAll<HTMLButtonElement>(".pin-menu button");
    expect(buttons.length).toBe(1);
    expect(buttons[0]?.textContent).toBe("Undo");
    buttons[0]?.click();
    expect(calls.undo).toBe(1);
    expect(pin.menuOpen).toBe(false);
  });

  it("disables Undo with the nothing-to-undo title when there is nothing to undo", async () => {
    const { pin } = await mount(new PinPositionStore(fakeArea()), false);
    pin.element.querySelector<HTMLButtonElement>('button[aria-label="kata"]')?.click();
    const undo = pin.element.querySelector<HTMLButtonElement>(".pin-menu button");
    expect(undo?.disabled).toBe(true);
    expect(undo?.title).toBe("Nothing to undo");
  });

  it("closes the mini-menu on Escape", async () => {
    const { pin } = await mount(new PinPositionStore(fakeArea()));
    pin.element.querySelector<HTMLButtonElement>('button[aria-label="kata"]')?.click();
    expect(pin.menuOpen).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flush();
    expect(pin.menuOpen).toBe(false);
  });
});
