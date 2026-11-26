/**
 * Floating card, joke cloud: one joke from the server list, with a close button.
 * The joke text is set as text, never as markup. Button text comes from TEXT_JOKE_CLOUD.
 */
import { TEXT_JOKE_CLOUD } from "../strings";
import { button, el } from "../dom";

const [CLOSE] = TEXT_JOKE_CLOUD;

/** Builds the joke card in the page; `onClose` closes it. */
export function renderJokeCloud(jokeText: string, onClose: () => void): HTMLElement {
  const card = el("div", undefined, "card joke-cloud");
  card.append(el("p", jokeText, "joke"));
  card.append(button(CLOSE, onClose, "x"));
  return card;
}
