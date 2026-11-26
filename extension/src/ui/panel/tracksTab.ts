import { el } from "../dom";
import { TEXT_SIGNIN, TEXT_TRACKS_TAB } from "../strings";

const [TITLE, EMPTY, OPEN, NEW_TRACK, SORT_BY, NAME_SORT, ADDED_SORT, VIEWED_SORT, RELEVANCE_SORT] = TEXT_TRACKS_TAB;
// Indexes into TEXT_TRACKS_TAB: the A to Z ... Least relevant labels are not used here.
const PROGRESS = TEXT_TRACKS_TAB[17];
const TOO_SLOW = TEXT_TRACKS_TAB[19];
const LOAD_FAILED = TEXT_TRACKS_TAB[20];
const UNREACHABLE = TEXT_SIGNIN[8];

/** What the tracks tab shows: a list, or one of the states from the inventory. */
export type TrackScreenState = "ready" | "empty" | "loading" | "error" | "offline";

/** Sort keys the tab offers; the caller sorts the rows it passes in. */
export type TrackSortKey = "name" | "added" | "viewed" | "relevance";

/** One row of the tracks tab: name, progress text and whether the pace is too slow. */
export interface TrackRowView {
  id: number;
  name: string;
  progress: string;
  tooSlow: boolean;
}

/** Props of the tracks tab: its state, the rows (ready only) and the current sort key. */
export interface TracksTabProps {
  state: TrackScreenState;
  rows: TrackRowView[];
  sort: TrackSortKey;
}

/** Handlers of the tracks tab: open one track, start a new one, change the sort key. */
export interface TracksTabHandlers {
  onOpen: (trackId: number) => void;
  onNew: () => void;
  onSort: (sort: TrackSortKey) => void;
}

const SORT_OPTIONS: Array<[TrackSortKey, string]> = [
  ["name", NAME_SORT],
  ["added", ADDED_SORT],
  ["viewed", VIEWED_SORT],
  ["relevance", RELEVANCE_SORT],
];

/**
 * Tracks tab: "You have no tracks yet." when empty, one row per track with its progress and a
 * "Too slow for the deadline." note, the sort control, and the New track button. Error and offline
 * states show their message in place of the list.
 */
export function renderTracksTab(props: TracksTabProps, handlers: TracksTabHandlers): HTMLElement {
  const screen = el("section", undefined, "tracks-tab");
  screen.dataset.state = props.state;
  screen.append(el("h2", TITLE));
  const newButton = el("button", NEW_TRACK, "new-track");
  newButton.type = "button";
  newButton.addEventListener("click", () => handlers.onNew());
  if (props.state === "loading") {
    screen.setAttribute("aria-busy", "true");
  } else if (props.state === "error") {
    screen.append(el("p", LOAD_FAILED, "error"));
  } else if (props.state === "offline") {
    screen.append(el("p", UNREACHABLE, "offline"));
  } else if (props.state === "empty") {
    screen.append(el("p", EMPTY, "empty"));
  } else {
    screen.append(renderControls(props.sort, handlers), renderList(props.rows, handlers));
  }
  screen.append(newButton);
  return screen;
}

function renderControls(sort: TrackSortKey, handlers: TracksTabHandlers): HTMLElement {
  const label = el("label", SORT_BY, "sort");
  const select = el("select");
  for (const [key, text] of SORT_OPTIONS) {
    const option = el("option", text);
    option.value = key;
    option.selected = key === sort;
    select.append(option);
  }
  select.addEventListener("change", () => handlers.onSort(select.value as TrackSortKey));
  label.append(select);
  return label;
}

function renderList(rows: TrackRowView[], handlers: TracksTabHandlers): HTMLElement {
  const list = el("ul", undefined, "track-list");
  for (const row of rows) {
    const item = el("li", undefined, "track-row");
    const open = el("button", OPEN, "open-track");
    open.type = "button";
    open.addEventListener("click", () => handlers.onOpen(row.id));
    item.append(el("span", row.name, "name"), el("span", `${PROGRESS}: ${row.progress}`, "progress"), open);
    if (row.tooSlow) item.append(el("span", TOO_SLOW, "too-slow"));
    list.append(item);
  }
  return list;
}
