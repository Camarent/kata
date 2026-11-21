import { describe, expect, it, vi } from "vitest";
import { openPanel } from "../src/browser";

describe("openPanel", () => {
  it("uses sidePanel.open with the window id when sidePanel exists", async () => {
    const sidePanelOpen = vi.fn(async () => undefined);
    const sidebarOpen = vi.fn(async () => undefined);
    await openPanel({ sidePanel: { open: sidePanelOpen }, sidebarAction: { open: sidebarOpen } }, 4);
    expect(sidePanelOpen).toHaveBeenCalledWith({ windowId: 4 });
    expect(sidebarOpen).not.toHaveBeenCalled();
  });

  it("falls back to sidebarAction.open when only sidebarAction exists", async () => {
    const sidebarOpen = vi.fn(async () => undefined);
    await openPanel({ sidebarAction: { open: sidebarOpen } }, 4);
    expect(sidebarOpen).toHaveBeenCalledOnce();
  });

  it("calls sidebarAction.open synchronously, before any await", () => {
    const sidebarOpen = vi.fn(async () => undefined);
    void openPanel({ sidebarAction: { open: sidebarOpen } }, 4);
    expect(sidebarOpen).toHaveBeenCalledOnce();
  });

  it("throws a clear error when neither API exists", () => {
    expect(() => openPanel({}, 4)).toThrow("neither sidePanel nor sidebarAction");
  });
});
