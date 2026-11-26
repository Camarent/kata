import { el } from "../dom";
import { SIGNIN_TEXT, TRACK_DETAIL_TEXT } from "../strings";
import type { TrackScreenState } from "./tracksTab";

// The sort and exam labels of TRACK_DETAIL_TEXT are not used on this screen.
const {
  title: TITLE,
  goal: GOAL_LABEL,
  deadline: DEADLINE_LABEL,
  progress: PROGRESS_LABEL,
  velocity: VELOCITY_LABEL,
  finishEarly: FINISH_EARLY,
  tooSlow: TOO_SLOW,
  dropReason: DROP_REASON,
  sources: SOURCES,
  addSource: ADD_SOURCE,
  quiz: QUIZ,
  back: BACK,
  noSources: NO_SOURCES,
  loadFailed: LOAD_FAILED,
} = TRACK_DETAIL_TEXT;
const UNREACHABLE = SIGNIN_TEXT.unreachable;

/** The track as the detail screen shows it. Progress and velocity are display text from the core. */
export interface TrackDetailView {
  name: string;
  goal: string;
  deadline: string;
  progress: string;
  velocity: string;
  finishEarly: boolean;
  tooSlow: boolean;
  /** Why progress dropped after a source was added; null when it did not drop. */
  dropReason: string | null;
  sources: string[];
}

/** Props of the detail screen: its state and the track (ready only). */
export interface TrackDetailProps {
  state: TrackScreenState;
  track: TrackDetailView | null;
}

/** Handlers of the detail screen: go back, add a source, start a quiz. */
export interface TrackDetailHandlers {
  onBack: () => void;
  onAddSource: () => void;
  onQuiz: () => void;
}

/**
 * Track detail: goal, deadline, progress and velocity, the finish-early and too-slow notes, the drop
 * reason, and the sources with "This track has no sources yet." when there are none. Error and
 * offline states show their message in place of the track. Back, Add source and Quiz always show.
 */
export function renderTrackDetail(props: TrackDetailProps, handlers: TrackDetailHandlers): HTMLElement {
  const screen = el("section", undefined, "track-detail");
  screen.dataset.state = props.state;
  screen.append(el("h2", TITLE));
  const track = props.track;
  if (props.state === "error") {
    screen.append(el("p", LOAD_FAILED, "error"));
  } else if (props.state === "offline") {
    screen.append(el("p", UNREACHABLE, "offline"));
  } else if (props.state === "loading") {
    screen.setAttribute("aria-busy", "true");
  } else if (track !== null) {
    screen.append(el("h3", track.name, "name"));
    screen.append(
      el("p", `${GOAL_LABEL}: ${track.goal}`, "goal"),
      el("p", `${DEADLINE_LABEL}: ${track.deadline}`, "deadline"),
      el("p", `${PROGRESS_LABEL}: ${track.progress}`, "progress"),
      el("p", `${VELOCITY_LABEL}: ${track.velocity}`, "velocity"),
    );
    if (track.finishEarly) screen.append(el("p", FINISH_EARLY, "finish-early"));
    if (track.tooSlow) screen.append(el("p", TOO_SLOW, "too-slow"));
    if (track.dropReason !== null) screen.append(el("p", DROP_REASON, "drop-reason"));
    screen.append(renderSources(track.sources));
  }
  screen.append(renderActions(handlers));
  return screen;
}

function renderSources(sources: string[]): HTMLElement {
  const box = el("div", undefined, "sources");
  box.append(el("h3", SOURCES));
  if (sources.length === 0) {
    box.append(el("p", NO_SOURCES, "empty"));
  } else {
    const list = el("ul");
    for (const source of sources) list.append(el("li", source));
    box.append(list);
  }
  return box;
}

function renderActions(handlers: TrackDetailHandlers): HTMLElement {
  const bar = el("div", undefined, "actions");
  const back = el("button", BACK, "back");
  back.type = "button";
  back.addEventListener("click", () => handlers.onBack());
  const addSource = el("button", ADD_SOURCE, "add-source");
  addSource.type = "button";
  addSource.addEventListener("click", () => handlers.onAddSource());
  const quiz = el("button", QUIZ, "quiz");
  quiz.type = "button";
  quiz.addEventListener("click", () => handlers.onQuiz());
  bar.append(back, addSource, quiz);
  return bar;
}
