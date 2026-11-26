/**
 * Focus mode (D50): one manual toggle that ends by itself after a chosen time, default 3 hours.
 * Every time check takes an injected clock, so tests pin time; the card passes `Date.now`.
 * Text comes from the approved strings (TEXT_FOCUS_CONFIRM).
 */
import { TEXT_FOCUS_CONFIRM } from "../strings";
import { button, el } from "../dom";

/** Returns the current time in epoch milliseconds. */
export type Clock = () => number;

/** Auto-end default in hours (D50). */
export const DEFAULT_FOCUS_HOURS = 3;

const MS_PER_HOUR = 60 * 60 * 1000;

/** Callbacks of the confirm card: `onTurnOn` gets the new end time, the others close it. */
export interface FocusActions {
  onTurnOn(endsAt: number): void;
  onTurnOff(): void;
  onCancel(): void;
}

const [TITLE, ENDS_AFTER, DURATION, WARNING, TURN_ON, TURN_OFF, CANCEL, ENDS_AT] =
  TEXT_FOCUS_CONFIRM;

/** End time (epoch ms) of a focus run that starts now and lasts `hours`. */
export function focusEndsAt(clock: Clock, hours: number = DEFAULT_FOCUS_HOURS): number {
  return clock() + hours * MS_PER_HOUR;
}

/** True while focus is on: an end time is set and the clock has not reached it. */
export function isFocusOn(endsAt: number | null, clock: Clock): boolean {
  return endsAt !== null && clock() < endsAt;
}

/** Local HH:MM of an end time, as the confirm card shows it. */
export function formatEndsAt(endsAt: number): string {
  const when = new Date(endsAt);
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${pad(when.getHours())}:${pad(when.getMinutes())}`;
}

/** The ends-at line: the approved inventory text with its example time swapped for `endsAt`. */
export function endsAtLine(endsAt: number): string {
  return ENDS_AT.replace(/\d{2}:\d{2}/, formatEndsAt(endsAt));
}

/** Builds the focus confirm card; the caller attaches it to the page. */
export function renderFocusConfirm(
  endsAt: number | null,
  clock: Clock,
  actions: FocusActions,
): HTMLElement {
  const card = el("div", undefined, "card focus-confirm");
  card.append(el("h2", TITLE));
  card.append(el("p", ENDS_AFTER, "ends-after"));
  card.append(el("p", DURATION, "duration"));
  card.append(el("p", WARNING));
  if (endsAt !== null && isFocusOn(endsAt, clock)) {
    card.append(el("p", endsAtLine(endsAt), "ends-at"));
    card.append(button(TURN_OFF, actions.onTurnOff, "turn-off"));
  } else {
    card.append(button(TURN_ON, () => actions.onTurnOn(focusEndsAt(clock)), "turn-on"));
  }
  card.append(button(CANCEL, actions.onCancel, "cancel"));
  return card;
}
