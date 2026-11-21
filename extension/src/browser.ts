/**
 * The part of the browser API that opens the side panel. Chrome exposes `sidePanel`;
 * Firefox exposes `sidebarAction`. Either one may be missing at runtime.
 */
export interface PanelOpenApi {
  sidePanel?: { open(options: { windowId: number }): Promise<void> };
  sidebarAction?: { open(): Promise<void> | void };
}

/**
 * Opens the side panel in windowId. Call it straight from the click handler: Firefox
 * rejects sidebarAction.open() when any await runs before it. Throws when the browser
 * offers neither API.
 */
export function openPanel(api: PanelOpenApi, windowId: number): Promise<void> {
  if (api.sidePanel) return api.sidePanel.open({ windowId });
  if (api.sidebarAction) return Promise.resolve(api.sidebarAction.open());
  throw new Error("openPanel: browser has neither sidePanel nor sidebarAction");
}
