import type { IgnoredConcept } from "./coreClientTypes";
import type { PanelMessage } from "./messages";
import type { PanelState } from "./sidepanel";
import type { IgnoredClient, IgnoredRowView } from "./ui/panel/ignoredList";

/** Sends one panel message and returns its data; the same sender the boot module uses. */
export type PanelSend = <T>(message: PanelMessage) => Promise<T>;

/**
 * Ignored concepts for the ignored list page, from the panel:ignored reply.
 * The caller passes the panel state and its message sender.
 */
export async function loadIgnored(state: PanelState, send: PanelSend): Promise<void> {
  const list = await send<IgnoredConcept[]>({ type: "panel:ignored" });
  state.ignored = list.map((concept): IgnoredRowView => ({ conceptId: concept.concept_id, label: concept.label }));
}

/** The two ignored calls the ignored list makes, each as one panel message. */
export function ignoredClient(send: PanelSend): IgnoredClient {
  return {
    ignoreConcept: (conceptId) => send<void>({ type: "panel:ignoreConcept", conceptId }),
    unignoreConcept: (conceptId) => send<void>({ type: "panel:unignoreConcept", conceptId }),
  };
}

/** After Restore or Undo the ignored list page reloads its rows from the core, then redraws. */
export async function refreshIgnored(state: PanelState, send: PanelSend, draw: () => void): Promise<void> {
  await loadIgnored(state, send);
  draw();
}

/**
 * Opens the ignored list page once its rows load; a refused list leaves the settings home drawn.
 * The caller passes the panel state, its message sender and its redraw.
 */
export async function openIgnoredPage(state: PanelState, send: PanelSend, draw: () => void): Promise<void> {
  try {
    await loadIgnored(state, send);
  } catch {
    // The list did not load: the settings home stays drawn.
    return;
  }
  state.settingsPage = "ignored";
  draw();
}
