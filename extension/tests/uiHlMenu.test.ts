import { afterEach, describe, expect, it, vi } from "vitest";
import { attachHlHover, renderHlMenu } from "../src/ui/overlay/hlMenu";
import type { HlMenuOptions } from "../src/ui/overlay/hlMenu";
import type { ScanConceptItem } from "../src/coreClientTypes";
import type { ReviewState } from "../src/messages";
import { TEXT_HL_HOVER_MENU, TEXT_HL_WHICH_ONE } from "../src/ui/strings";

function item(over: Partial<ScanConceptItem> = {}): ScanConceptItem {
  return {
    word: "SYN",
    conceptId: 7,
    label: "SYN",
    definition: "first step of the TCP handshake",
    state: "new",
    candidates: [{ conceptId: 8, label: "SYN-ACK" }],
    ...over,
  };
}

function optsOf(over: Partial<HlMenuOptions> = {}): HlMenuOptions {
  return {
    topicId: 3,
    word: "SYN",
    item: item(),
    offline: false,
    client: { chooseConcept: vi.fn(async () => {}), reassignConcept: vi.fn(async () => {}) },
    onState: vi.fn(),
    ...over,
  };
}

function pressed(root: HTMLElement): string | undefined {
  return root.querySelector<HTMLButtonElement>('button.state-button[aria-pressed="true"]')?.textContent ?? undefined;
}

/** Lets the promise chains of button clicks settle. */
function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("renderHlMenu", () => {
  it.each([
    ["new", "New"],
    ["learning", "Learning"],
    ["known", "Known"],
  ] as [ReviewState, string][])("state %s shows the %s button pressed", (state, label) => {
    const root = renderHlMenu(optsOf({ item: item({ state }) }), vi.fn());
    expect(pressed(root)).toBe(label);
    const labels = [...root.querySelectorAll("button.state-button")].map((b) => b.textContent);
    expect(labels).toEqual(["New", "Learning", "Known"]);
  });

  it("shows the concept name and the one-line definition", () => {
    const root = renderHlMenu(optsOf(), vi.fn());
    expect(root.querySelector(".concept")?.textContent).toBe("SYN");
    expect(root.querySelector(".definition")?.textContent).toBe("first step of the TCP handshake");
  });

  it("offline shows the Not synced note", () => {
    const root = renderHlMenu(optsOf({ offline: true }), vi.fn());
    expect(root.querySelector(".offline")?.textContent).toBe(TEXT_HL_HOVER_MENU[6]);
  });

  it("online shows no Not synced note", () => {
    const root = renderHlMenu(optsOf({ offline: false }), vi.fn());
    expect(root.querySelector(".offline")).toBeNull();
  });

  it("with no other meaning known shows the note and no Not this meaning button", () => {
    const root = renderHlMenu(optsOf({ item: item({ candidates: [] }) }), vi.fn());
    expect(root.querySelector(".not-this-meaning")).toBeNull();
    expect(root.querySelector(".no-meaning")?.textContent).toBe(TEXT_HL_HOVER_MENU[5]);
  });

  it("a state button calls onState with that state", () => {
    const onState = vi.fn();
    const root = renderHlMenu(optsOf({ onState }), vi.fn());
    root.querySelector<HTMLButtonElement>("button.state-known")?.click();
    expect(onState).toHaveBeenCalledWith("known");
  });

  it("Not this meaning shows the Which one? list and a pick calls chooseConcept then reassignConcept", async () => {
    const client = { chooseConcept: vi.fn(async () => {}), reassignConcept: vi.fn(async () => {}) };
    const shown: HTMLElement[] = [];
    const root = renderHlMenu(optsOf({ client }), (content) => shown.push(content));
    root.querySelector<HTMLButtonElement>(".not-this-meaning")?.click();
    expect(shown).toHaveLength(1);
    const which = shown[0];
    expect(which.querySelector(".title")?.textContent).toBe(TEXT_HL_WHICH_ONE[0]);
    which.querySelector<HTMLButtonElement>("button.candidate")?.click();
    await settle();
    expect(client.chooseConcept).toHaveBeenCalledWith(3, "SYN", 8);
    expect(client.reassignConcept).toHaveBeenCalledWith(3, "SYN", 7, 8);
  });

  it("a second pick in the same menu reassigns from the first pick", async () => {
    const client = { chooseConcept: vi.fn(async () => {}), reassignConcept: vi.fn(async () => {}) };
    const shown: HTMLElement[] = [];
    const two = item({
      candidates: [
        { conceptId: 8, label: "SYN-ACK" },
        { conceptId: 9, label: "SYN flood" },
      ],
    });
    const root = renderHlMenu(optsOf({ client, item: two }), (content) => shown.push(content));
    root.querySelector<HTMLButtonElement>(".not-this-meaning")?.click();
    const buttons = shown[0].querySelectorAll<HTMLButtonElement>("button.candidate");
    buttons[0].click();
    await settle();
    buttons[1].click();
    await settle();
    expect(client.reassignConcept).toHaveBeenNthCalledWith(1, 3, "SYN", 7, 8);
    expect(client.reassignConcept).toHaveBeenNthCalledWith(2, 3, "SYN", 8, 9);
  });

  it.each([
    ["the pick is the current concept", item({ conceptId: 8 })],
    ["the highlight has no concept", item({ conceptId: null })],
  ])("no reassignConcept when %s", async (_name, it2) => {
    const client = { chooseConcept: vi.fn(async () => {}), reassignConcept: vi.fn(async () => {}) };
    const shown: HTMLElement[] = [];
    const root = renderHlMenu(optsOf({ client, item: it2 }), (content) => shown.push(content));
    root.querySelector<HTMLButtonElement>(".not-this-meaning")?.click();
    shown[0].querySelector<HTMLButtonElement>("button.candidate")?.click();
    await settle();
    expect(client.chooseConcept).toHaveBeenCalledWith(3, "SYN", 8);
    expect(client.reassignConcept).not.toHaveBeenCalled();
  });

  it("a failed chooseConcept shows its error and skips reassignConcept", async () => {
    const client = {
      chooseConcept: vi.fn(async () => {
        throw new Error("choose failed");
      }),
      reassignConcept: vi.fn(async () => {}),
    };
    const shown: HTMLElement[] = [];
    const root = renderHlMenu(optsOf({ client }), (content) => shown.push(content));
    root.querySelector<HTMLButtonElement>(".not-this-meaning")?.click();
    shown[0].querySelector<HTMLButtonElement>("button.candidate")?.click();
    await settle();
    expect(client.reassignConcept).not.toHaveBeenCalled();
    expect(shown[0].querySelector(".note")?.textContent).toBe("choose failed");
  });

  it("a failed reassignConcept shows its error", async () => {
    const client = {
      chooseConcept: vi.fn(async () => {}),
      reassignConcept: vi.fn(async () => {
        throw new Error("reassign failed");
      }),
    };
    const shown: HTMLElement[] = [];
    const root = renderHlMenu(optsOf({ client }), (content) => shown.push(content));
    root.querySelector<HTMLButtonElement>(".not-this-meaning")?.click();
    shown[0].querySelector<HTMLButtonElement>("button.candidate")?.click();
    await settle();
    expect(shown[0].querySelector(".note")?.textContent).toBe("reassign failed");
  });

  it("a word with replace patterns is shown literally in the Which one? list", () => {
    const shown: HTMLElement[] = [];
    const root = renderHlMenu(optsOf({ word: "a$&b$'c" }), (content) => shown.push(content));
    root.querySelector<HTMLButtonElement>(".not-this-meaning")?.click();
    expect(shown[0].querySelector(".word")?.textContent).toBe("Word on the page: a$&b$'c");
  });
});

describe("attachHlHover", () => {
  const cleanups: (() => void)[] = [];
  const hosts: HTMLElement[] = [];

  function hostWord(): HTMLElement {
    const host = document.createElement("span");
    host.textContent = "SYN";
    document.body.append(host);
    hosts.push(host);
    return host;
  }

  afterEach(() => {
    for (const off of cleanups.splice(0)) off();
    for (const host of hosts.splice(0)) host.remove();
  });

  it("hover opens the menu and adds no style or class change to the word", () => {
    const host = hostWord();
    cleanups.push(attachHlHover(host, optsOf()));
    const styleBefore = host.getAttribute("style");
    const classBefore = host.className;
    host.dispatchEvent(new MouseEvent("mouseenter"));
    const popover = document.querySelector<HTMLElement>(".popover");
    expect(popover?.hidden).toBe(false);
    expect(popover?.style.position).toBe("absolute");
    expect(popover?.querySelector(".hl-hover-menu")).not.toBeNull();
    expect(host.getAttribute("style")).toBe(styleBefore);
    expect(host.className).toBe(classBefore);
  });

  it("focus leaving the word and the menu closes the popover", () => {
    const host = hostWord();
    cleanups.push(attachHlHover(host, optsOf()));
    host.dispatchEvent(new FocusEvent("focus"));
    const popover = document.querySelector<HTMLElement>(".popover");
    expect(popover?.hidden).toBe(false);
    host.dispatchEvent(new FocusEvent("focusout", { relatedTarget: popover }));
    expect(popover?.hidden).toBe(false);
    host.dispatchEvent(new FocusEvent("focusout", { relatedTarget: document.body }));
    expect(popover?.hidden).toBe(true);
  });

  it("the cleanup removes the popover and its listeners", () => {
    const host = hostWord();
    const off = attachHlHover(host, optsOf());
    const pop = document.querySelector<HTMLElement>(".popover");
    off();
    const docListen = vi.spyOn(document, "addEventListener");
    cleanups.push(() => docListen.mockRestore());
    host.dispatchEvent(new MouseEvent("mouseenter"));
    expect(document.querySelector(".popover")).toBeNull();
    // A leaked openAt would reopen the detached popover and add document listeners.
    expect(pop?.hidden).toBe(true);
    expect(docListen).not.toHaveBeenCalled();
  });
});
