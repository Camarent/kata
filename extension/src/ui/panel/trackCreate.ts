import { CoreOfflineError, CoreTimeoutError } from "../../coreClient";
import { el } from "../dom";
import { TEXT_SIGNIN, TEXT_TRACK_CREATE } from "../strings";

const [TITLE, NAME_LABEL, GOAL_LABEL, DEADLINE_LABEL, BUDGET_LABEL, CREATE, CANCEL, FAILED] = TEXT_TRACK_CREATE;
const UNREACHABLE = TEXT_SIGNIN[8];

/** What the create form shows: the form itself, a failed save, or an offline core. */
export type TrackCreateState = "form" | "error" | "offline";

/** Props of the create form: the state of the last save attempt. */
export interface TrackCreateProps {
  state: TrackCreateState;
}

/** The values the form sends. `minutes` is the optional time budget and is absent when left empty. */
export interface TrackCreateInput {
  name: string;
  goal: string;
  deadline: string;
  minutes?: number;
}

/** Handlers of the create form: save the track (rejects when it fails) and leave the form. */
export interface TrackCreateHandlers {
  onCreate: (input: TrackCreateInput) => void | Promise<void>;
  onCancel: () => void;
}

/**
 * Create-track form: name, goal, deadline and an optional time budget in minutes. A blank name or
 * deadline, or a time budget that is not a positive whole number, sends nothing. While onCreate runs the submit is disabled. A rejected save shows
 * "Server not reachable." when the core is offline or times out, else "Could not create the track.".
 */
export function renderTrackCreate(props: TrackCreateProps, handlers: TrackCreateHandlers): HTMLElement {
  const form = el("form", undefined, "track-create");
  form.dataset.state = props.state;
  form.append(el("h2", TITLE));
  const name = field(form, NAME_LABEL, "name");
  const goal = field(form, GOAL_LABEL, "goal");
  const deadline = field(form, DEADLINE_LABEL, "deadline");
  deadline.type = "date";
  const budget = field(form, BUDGET_LABEL, "minutes");
  budget.inputMode = "numeric";
  const submit = el("button", CREATE);
  submit.type = "submit";
  const cancel = el("button", CANCEL);
  cancel.type = "button";
  cancel.addEventListener("click", () => handlers.onCancel());
  form.append(submit, cancel);
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  if (props.state === "error") error.textContent = FAILED;
  if (props.state === "offline") error.textContent = UNREACHABLE;
  form.append(error);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input: TrackCreateInput = {
      name: name.value.trim(),
      goal: goal.value.trim(),
      deadline: deadline.value.trim(),
    };
    const minutes = budget.value.trim();
    if (minutes !== "") {
      const value = Number(minutes);
      if (!Number.isInteger(value) || value <= 0) return;
      input.minutes = value;
    }
    if (input.name === "" || input.deadline === "") return;
    error.textContent = "";
    submit.disabled = true;
    try {
      await handlers.onCreate(input);
    } catch (err) {
      const offline = err instanceof CoreOfflineError || err instanceof CoreTimeoutError;
      error.textContent = offline ? UNREACHABLE : FAILED;
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

/** Appends a labelled text input to `form` and returns it. */
function field(form: HTMLElement, text: string, inputName: string): HTMLInputElement {
  const label = el("label", text);
  const input = el("input");
  input.name = inputName;
  input.type = "text";
  label.append(input);
  form.append(label);
  return input;
}
