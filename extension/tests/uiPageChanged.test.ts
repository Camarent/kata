import { describe, expect, it, vi } from "vitest";
import { renderPageChanged } from "../src/ui/overlay/pageChanged";
import { TEXT_PAGE_CHANGED } from "../src/ui/strings";

describe("page changed prompt", () => {
  it("renders the inventory title and body strings", () => {
    const card = renderPageChanged(document, { onAction: vi.fn(), onBack: vi.fn() });
    expect(card.querySelector("h2")?.textContent).toBe(TEXT_PAGE_CHANGED[0]);
    expect(card.querySelector("p")?.textContent).toBe(TEXT_PAGE_CHANGED[2]);
    const labels = [...card.querySelectorAll("button")].map((b) => b.textContent);
    expect(labels).toEqual([TEXT_PAGE_CHANGED[5], TEXT_PAGE_CHANGED[6]]);
  });

  it("the action button calls onAction and not onBack", () => {
    const onAction = vi.fn();
    const onBack = vi.fn();
    const card = renderPageChanged(document, { onAction, onBack });
    card.querySelector<HTMLButtonElement>(".page-changed-action")?.click();
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onBack).not.toHaveBeenCalled();
  });

  it("the Back button calls onBack", () => {
    const onAction = vi.fn();
    const onBack = vi.fn();
    const card = renderPageChanged(document, { onAction, onBack });
    card.querySelector<HTMLButtonElement>(".x")?.click();
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onAction).not.toHaveBeenCalled();
  });
});
