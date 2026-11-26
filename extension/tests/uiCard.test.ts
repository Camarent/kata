import { describe, expect, it, vi } from "vitest";
import { renderCardMain } from "../src/ui/card/cardMain";
import { renderCardScan } from "../src/ui/card/cardScan";
import { renderCardSummary } from "../src/ui/card/cardSummary";
import {
  DEFAULT_FOCUS_HOURS,
  focusEndsAt,
  formatEndsAt,
  isFocusOn,
  renderFocusConfirm,
} from "../src/ui/card/focus";
import { renderJokeCloud } from "../src/ui/card/jokeCloud";
import {
  TEXT_CARD_MAIN,
  TEXT_CARD_SCAN,
  TEXT_CARD_SUMMARY,
  TEXT_FOCUS_CONFIRM,
  TEXT_JOKE_CLOUD,
} from "../src/ui/strings";

/** Text of every button in a rendered card, in order. */
const buttonLabels = (card: HTMLElement): (string | null)[] =>
  [...card.querySelectorAll("button")].map((b) => b.textContent);

/** Text of every paragraph in a rendered card, in order. */
const paragraphs = (card: HTMLElement): (string | null)[] =>
  [...card.querySelectorAll("p")].map((p) => p.textContent);

const noopMainActions = {
  onScan: vi.fn(),
  onSummary: vi.fn(),
  onQuiz: vi.fn(),
  onFocus: vi.fn(),
  onOpenPanel: vi.fn(),
  onCollapse: vi.fn(),
};

describe("floating card, main screen", () => {
  it("before any scan shows the no-scan text and the inventory button labels", () => {
    const card = renderCardMain({ counts: null, serverDown: false, focusOn: false }, noopMainActions);
    expect(card.querySelector("h3")?.textContent).toBe(TEXT_CARD_MAIN[3]);
    expect(paragraphs(card)).toContain(TEXT_CARD_MAIN[4]);
    expect(buttonLabels(card)).toEqual([
      TEXT_CARD_MAIN[5],
      TEXT_CARD_MAIN[6],
      TEXT_CARD_MAIN[7],
      TEXT_CARD_MAIN[8],
      TEXT_CARD_MAIN[9],
      TEXT_CARD_MAIN[10],
    ]);
    expect(paragraphs(card)).toContain(TEXT_CARD_MAIN[12]);
  });

  it("after a scan lists the New, Learning and Known counts", () => {
    const card = renderCardMain(
      { counts: { new: 12, learning: 7, known: 5 }, serverDown: false, focusOn: false },
      noopMainActions,
    );
    const items = [...card.querySelectorAll("li")].map((li) => li.textContent);
    expect(items).toEqual([
      `${TEXT_CARD_MAIN[0]}: 12`,
      `${TEXT_CARD_MAIN[1]}: 7`,
      `${TEXT_CARD_MAIN[2]}: 5`,
    ]);
    expect(card.querySelector(".no-scan")).toBeNull();
  });

  it("server down shows the notice and turns Scan and Quiz off", () => {
    const card = renderCardMain({ counts: null, serverDown: true, focusOn: false }, noopMainActions);
    expect(paragraphs(card)).toContain(TEXT_CARD_MAIN[11]);
    expect(card.querySelector<HTMLButtonElement>(".scan")?.disabled).toBe(true);
    expect(card.querySelector<HTMLButtonElement>(".quiz")?.disabled).toBe(true);
    expect(card.querySelector<HTMLButtonElement>(".summary")?.disabled).toBe(false);
  });

  it("each button calls its own action", () => {
    const actions = {
      onScan: vi.fn(),
      onSummary: vi.fn(),
      onQuiz: vi.fn(),
      onFocus: vi.fn(),
      onOpenPanel: vi.fn(),
      onCollapse: vi.fn(),
    };
    const card = renderCardMain({ counts: null, serverDown: false, focusOn: true }, actions);
    card.querySelector<HTMLButtonElement>(".scan")?.click();
    card.querySelector<HTMLButtonElement>(".summary")?.click();
    card.querySelector<HTMLButtonElement>(".quiz")?.click();
    card.querySelector<HTMLButtonElement>(".focus")?.click();
    card.querySelector<HTMLButtonElement>(".open-panel")?.click();
    card.querySelector<HTMLButtonElement>(".x")?.click();
    for (const fn of Object.values(actions)) expect(fn).toHaveBeenCalledTimes(1);
  });

  it("marks the focus button while focus is on", () => {
    const card = renderCardMain({ counts: null, serverDown: false, focusOn: true }, noopMainActions);
    expect(card.querySelector(".focus")).not.toBeNull();
    expect(card.querySelector(".focus.on")).not.toBeNull();
    const off = renderCardMain({ counts: null, serverDown: false, focusOn: false }, noopMainActions);
    expect(off.querySelector(".focus.on")).toBeNull();
  });
});

describe("floating card, scan screen", () => {
  const actions = { onShowInPanel: vi.fn(), onScanAgain: vi.fn(), onBack: vi.fn() };

  it("while scanning shows the scanning text and no Scan again", () => {
    const card = renderCardScan({ status: { kind: "scanning" }, focusOn: false }, actions);
    expect(paragraphs(card)).toEqual([TEXT_CARD_SCAN[0]]);
    expect(buttonLabels(card)).toEqual([TEXT_CARD_SCAN[4], TEXT_CARD_SCAN[6]]);
  });

  it("done shows the found-concepts line with the counts", () => {
    const card = renderCardScan(
      { status: { kind: "done", counts: { new: 12, learning: 7, known: 5 } }, focusOn: false },
      actions,
    );
    expect(paragraphs(card)).toEqual([TEXT_CARD_SCAN[1]]);
    expect(buttonLabels(card)).toEqual([TEXT_CARD_SCAN[4], TEXT_CARD_SCAN[5], TEXT_CARD_SCAN[6]]);
  });

  it("done puts total, new, learning and known in the right slots", () => {
    const card = renderCardScan(
      { status: { kind: "done", counts: { new: 3, learning: 1, known: 2 } }, focusOn: false },
      actions,
    );
    expect(paragraphs(card)).toEqual(["Found 6 concepts: 3 New, 1 Learning, 2 Known."]);
  });

  it("empty and error show their inventory text", () => {
    const empty = renderCardScan({ status: { kind: "empty" }, focusOn: false }, actions);
    expect(paragraphs(empty)).toEqual([TEXT_CARD_SCAN[2]]);
    const error = renderCardScan({ status: { kind: "error" }, focusOn: false }, actions);
    expect(paragraphs(error)).toEqual([TEXT_CARD_SCAN[3]]);
  });

  it("server down shows its notice and turns Scan again off", () => {
    const card = renderCardScan({ status: { kind: "serverDown" }, focusOn: false }, actions);
    expect(paragraphs(card)).toEqual([TEXT_CARD_SCAN[8]]);
    expect(card.querySelector<HTMLButtonElement>(".scan-again")?.disabled).toBe(true);
  });

  it("focus on adds the panel-only note", () => {
    const card = renderCardScan({ status: { kind: "empty" }, focusOn: true }, actions);
    expect(paragraphs(card)).toEqual([TEXT_CARD_SCAN[2], TEXT_CARD_SCAN[7]]);
  });
});

describe("floating card, summary screen", () => {
  const actions = { onOpenInPanel: vi.fn(), onBack: vi.fn() };

  it("needs a scan first", () => {
    const card = renderCardSummary({ kind: "needsScan" }, actions);
    expect(card.querySelector("h2")?.textContent).toBe(TEXT_CARD_SUMMARY[0]);
    expect(paragraphs(card)).toEqual([TEXT_CARD_SUMMARY[3]]);
    expect(buttonLabels(card)).toEqual([TEXT_CARD_SUMMARY[6], TEXT_CARD_SUMMARY[7]]);
  });

  it("loading and error show their inventory text", () => {
    expect(paragraphs(renderCardSummary({ kind: "loading" }, actions))).toEqual([TEXT_CARD_SUMMARY[4]]);
    expect(paragraphs(renderCardSummary({ kind: "error" }, actions))).toEqual([TEXT_CARD_SUMMARY[5]]);
  });

  it("ready shows the page text summary and the topics found", () => {
    const card = renderCardSummary(
      { kind: "ready", text: "A page about TCP.", topics: ["Networking basics", "SYN-ACK"] },
      actions,
    );
    const headings = [...card.querySelectorAll("h3")].map((h) => h.textContent);
    expect(headings).toEqual([TEXT_CARD_SUMMARY[1], TEXT_CARD_SUMMARY[2]]);
    expect(paragraphs(card)).toEqual(["A page about TCP."]);
    const topics = [...card.querySelectorAll("li")].map((li) => li.textContent);
    expect(topics).toEqual(["Networking basics", "SYN-ACK"]);
  });
});

describe("focus mode confirm (D50)", () => {
  const actions = () => ({ onTurnOn: vi.fn(), onTurnOff: vi.fn(), onCancel: vi.fn() });

  it("defaults to a 3 hour auto-end, matching the inventory text", () => {
    expect(DEFAULT_FOCUS_HOURS).toBe(3);
    expect(`${DEFAULT_FOCUS_HOURS} hours`).toBe(TEXT_FOCUS_CONFIRM[2]);
  });

  it("focus starts with the injected clock plus the default hours", () => {
    const now = Date.UTC(2026, 10, 26, 9, 0);
    expect(focusEndsAt(() => now)).toBe(now + 3 * 60 * 60 * 1000);
    expect(focusEndsAt(() => now, 1)).toBe(now + 60 * 60 * 1000);
  });

  it("focus is on until the clock reaches the end time, then it is off by itself", () => {
    const start = Date.UTC(2026, 10, 26, 9, 0);
    const endsAt = focusEndsAt(() => start);
    expect(isFocusOn(endsAt, () => start + 2 * 60 * 60 * 1000)).toBe(true);
    expect(isFocusOn(endsAt, () => endsAt - 1)).toBe(true);
    expect(isFocusOn(endsAt, () => endsAt)).toBe(false);
    expect(isFocusOn(null, () => start)).toBe(false);
  });

  it("off shows Turn on and Cancel; Turn on passes the end time from the clock", () => {
    const now = Date.UTC(2026, 10, 26, 9, 0);
    const a = actions();
    const card = renderFocusConfirm(null, () => now, a);
    expect(card.querySelector("h2")?.textContent).toBe(TEXT_FOCUS_CONFIRM[0]);
    expect(card.querySelector(".duration")?.textContent).toBe(TEXT_FOCUS_CONFIRM[2]);
    expect(buttonLabels(card)).toEqual([TEXT_FOCUS_CONFIRM[4], TEXT_FOCUS_CONFIRM[6]]);
    card.querySelector<HTMLButtonElement>(".turn-on")?.click();
    expect(a.onTurnOn).toHaveBeenCalledWith(now + 3 * 60 * 60 * 1000);
  });

  it("on shows the end time and Turn off; the clock decides when it is on", () => {
    const start = new Date(2026, 10, 26, 9, 0).getTime();
    const endsAt = focusEndsAt(() => start);
    const a = actions();
    const card = renderFocusConfirm(endsAt, () => start + 1000, a);
    // start 09:00 local + 3 h; literal pins the HH:MM format
    expect(paragraphs(card)).toContain("Focus mode ends at 12:00.");
    expect(formatEndsAt(new Date(2026, 10, 26, 9, 5).getTime())).toBe("09:05");
    expect(buttonLabels(card)).toEqual([TEXT_FOCUS_CONFIRM[5], TEXT_FOCUS_CONFIRM[6]]);
    card.querySelector<HTMLButtonElement>(".turn-off")?.click();
    expect(a.onTurnOff).toHaveBeenCalledTimes(1);
  });

  it("after the end time the card shows Turn on again", () => {
    const start = new Date(2026, 10, 26, 9, 0).getTime();
    const endsAt = focusEndsAt(() => start);
    const card = renderFocusConfirm(endsAt, () => endsAt + 1, actions());
    expect(buttonLabels(card)).toEqual([TEXT_FOCUS_CONFIRM[4], TEXT_FOCUS_CONFIRM[6]]);
  });

  it("Cancel calls onCancel", () => {
    const a = actions();
    const card = renderFocusConfirm(null, () => 0, a);
    card.querySelector<HTMLButtonElement>(".cancel")?.click();
    expect(a.onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("joke cloud", () => {
  it("shows the joke text and a Close joke button that calls onClose", () => {
    const onClose = vi.fn();
    const card = renderJokeCloud("Why did the packet cross the road?", onClose);
    expect(paragraphs(card)).toEqual(["Why did the packet cross the road?"]);
    expect(buttonLabels(card)).toEqual([TEXT_JOKE_CLOUD[0]]);
    card.querySelector<HTMLButtonElement>(".x")?.click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
