/** Creates an element with text content; never parses markup. */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className !== undefined) node.className = className;
  return node;
}

/** Creates a type=button element with a click handler; the label is text, never markup. */
export function button(
  label: string,
  onClick: () => void,
  className?: string,
  disabled = false,
): HTMLButtonElement {
  const node = el("button", label, className);
  node.type = "button";
  node.disabled = disabled;
  node.addEventListener("click", () => onClick());
  return node;
}
