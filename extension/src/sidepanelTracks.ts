import type { PanelMessage } from "./messages";
import type { PanelState } from "./sidepanel";
import type { Track, TrackPage } from "./coreClientTypes";
import type { TrackDetailView } from "./ui/panel/trackDetail";
import type { TrackCreateHandlers } from "./ui/panel/trackCreate";
import type { TrackRowView, TrackSortKey } from "./ui/panel/tracksTab";

/** One track as the Tracks tab draws it. The core sends no progress or pace, so the status stands in for progress. */
export function trackRowView(track: Track): TrackRowView {
  return { id: track.id, name: track.name, progress: track.status, tooSlow: false };
}

/**
 * One track as the detail screen draws it. The core Track has no goal, progress, velocity or pace flags,
 * so those take neutral empty values (open work in docs/roadmap.md); the items stand in for the sources.
 */
export function trackDetailView(track: Track): TrackDetailView {
  return {
    name: track.name,
    goal: "",
    deadline: track.deadline,
    progress: "",
    velocity: "",
    finishEarly: false,
    tooSlow: false,
    dropReason: null,
    sources: track.items.map((item) => item.label),
  };
}

/** Rows in the order the sort key asks for; only the name sort reorders, the others keep the core order. */
export function sortTrackRows(rows: TrackRowView[], sort: TrackSortKey): TrackRowView[] {
  return sort === "name" ? [...rows].sort((a, b) => a.name.localeCompare(b.name)) : rows;
}

/**
 * Loads the Tracks tab from the panel:tracks reply; a refused list shows the could-not-load state.
 * The caller passes the panel state, its message sender and its redraw.
 */
export async function loadTrackList(
  state: PanelState,
  send: <T>(message: PanelMessage) => Promise<T>,
  draw: () => void,
): Promise<void> {
  const sort = state.tracks?.sort ?? "name";
  state.tracks = { state: "loading", rows: [], sort };
  draw();
  try {
    const page = await send<TrackPage>({ type: "panel:tracks" });
    const rows = page.items.map(trackRowView);
    state.trackViews = Object.fromEntries(page.items.map((track) => [track.id, trackDetailView(track)]));
    state.tracks = { state: rows.length === 0 ? "empty" : "ready", rows: sortTrackRows(rows, sort), sort };
  } catch {
    state.tracks = { state: "error", rows: [], sort };
  }
  draw();
}

/** Steps between the track screens: back to the list, open add-source or quiz from the detail, back to the detail. */
export function trackScreenNav(
  state: PanelState,
  draw: () => void,
): { backFromTrack: () => void; openFromDetail: (kind: "source-add" | "quiz") => void; backToDetail: () => void } {
  /** Track the detail, add-source or quiz screen belongs to; undefined when no such screen is open. */
  const shownTrackId = (): number | undefined => {
    const screen = state.trackScreen;
    return screen === undefined || screen === null || screen.kind === "create" ? undefined : screen.trackId;
  };
  return {
    backFromTrack: () => {
      state.trackScreen = null;
      draw();
    },
    openFromDetail: (kind) => {
      const trackId = shownTrackId();
      if (trackId === undefined) return;
      state.trackScreen = { kind, trackId };
      draw();
    },
    backToDetail: () => {
      const trackId = shownTrackId();
      state.trackScreen = trackId === undefined ? null : { kind: "detail", trackId };
      draw();
    },
  };
}

/** What the create-track form needs from the panel: its state, the panel message sender, the list reload and the back step. */
export interface TrackCreateDeps {
  state: PanelState;
  send: <T>(message: PanelMessage) => Promise<T>;
  loadTracks: () => Promise<void>;
  onCancel: () => void;
}

/** Create-track form handlers: save sends the name and deadline, then the list reloads; cancel goes back. */
export function trackCreateHandlers(deps: TrackCreateDeps): TrackCreateHandlers {
  return {
    // A refused save rejects: the form shows its error line and stays open. The core takes only a name and deadline.
    async onCreate(input) {
      await deps.send<Track>({ type: "panel:createTrack", input: { name: input.name, deadline: input.deadline } });
      deps.state.trackScreen = null;
      await deps.loadTracks();
    },
    onCancel: deps.onCancel,
  };
}
