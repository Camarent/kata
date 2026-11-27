import { afterEach, describe, expect, it, vi } from "vitest";
import { CoreOfflineError, CoreTimeoutError } from "../src/coreClient";
import { renderTrackCreate } from "../src/ui/panel/trackCreate";
import { renderTrackDetail, type TrackDetailView } from "../src/ui/panel/trackDetail";
import { renderTracksTab, type TrackRowView } from "../src/ui/panel/tracksTab";

const UNREACHABLE = "Server not reachable.";

const rows: TrackRowView[] = [
  { id: 1, name: "Algebra", progress: "40%", tooSlow: true },
  { id: 2, name: "Biology", progress: "10%", tooSlow: false },
];

const track: TrackDetailView = {
  name: "Algebra",
  goal: "Solve quadratics",
  deadline: "2026-12-31",
  progress: "40%",
  velocity: "2 concepts a week",
  finishEarly: false,
  tooSlow: false,
  dropReason: null,
  sources: ["Chapter 3"],
};

function tabHandlers() {
  return { onOpen: vi.fn(), onNew: vi.fn(), onSort: vi.fn() };
}

function detailHandlers() {
  return { onBack: vi.fn(), onAddSource: vi.fn(), onQuiz: vi.fn() };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("tracks tab", () => {
  it("ready: one row per track with progress, the too-slow note and the sort control", () => {
    const handlers = tabHandlers();
    const screen = renderTracksTab({ state: "ready", rows, sort: "name" }, handlers);
    expect(screen.dataset.state).toBe("ready");
    expect(screen.querySelectorAll(".track-row")).toHaveLength(2);
    expect(screen.querySelector(".track-row .name")?.textContent).toBe("Algebra");
    expect(screen.querySelector(".track-row .progress")?.textContent).toBe("Progress: 40%");
    expect(screen.querySelectorAll(".too-slow")).toHaveLength(1);
    expect(screen.querySelector(".too-slow")?.textContent).toBe("Too slow for the deadline.");
    const sort = screen.querySelector<HTMLSelectElement>(".sort select");
    expect(sort?.value).toBe("name");
    expect(Array.from(sort?.options ?? []).map((o) => o.textContent)).toEqual([
      "Name",
      "Added date",
      "Last viewed",
      "Relevance",
    ]);
  });

  it("ready: Open track calls onOpen with the row id, New track calls onNew", () => {
    const handlers = tabHandlers();
    const screen = renderTracksTab({ state: "ready", rows, sort: "name" }, handlers);
    const opens = screen.querySelectorAll<HTMLButtonElement>(".open-track");
    opens[1]?.click();
    expect(handlers.onOpen).toHaveBeenCalledWith(2);
    screen.querySelector<HTMLButtonElement>(".new-track")?.click();
    expect(handlers.onNew).toHaveBeenCalledOnce();
  });

  it("ready: changing the sort select calls onSort with the key", () => {
    const handlers = tabHandlers();
    const screen = renderTracksTab({ state: "ready", rows, sort: "name" }, handlers);
    const sort = screen.querySelector<HTMLSelectElement>(".sort select");
    if (sort) {
      sort.value = "viewed";
      sort.dispatchEvent(new Event("change"));
    }
    expect(handlers.onSort).toHaveBeenCalledWith("viewed");
  });

  it("empty: shows the empty text and New track, no list", () => {
    const screen = renderTracksTab({ state: "empty", rows: [], sort: "name" }, tabHandlers());
    expect(screen.querySelector(".empty")?.textContent).toBe("You have no tracks yet.");
    expect(screen.querySelector(".track-list")).toBeNull();
    expect(screen.querySelector(".new-track")?.textContent).toBe("New track");
  });

  it("loading: no list and no message, marked busy", () => {
    const screen = renderTracksTab({ state: "loading", rows: [], sort: "name" }, tabHandlers());
    expect(screen.getAttribute("aria-busy")).toBe("true");
    expect(screen.querySelector(".track-list")).toBeNull();
    expect(screen.querySelector(".error")).toBeNull();
  });

  it("error: shows Could not load tracks.", () => {
    const screen = renderTracksTab({ state: "error", rows: [], sort: "name" }, tabHandlers());
    expect(screen.querySelector(".error")?.textContent).toBe("Could not load tracks.");
    expect(screen.querySelector(".track-list")).toBeNull();
  });

  it("offline: shows Server not reachable.", () => {
    const screen = renderTracksTab({ state: "offline", rows: [], sort: "name" }, tabHandlers());
    expect(screen.querySelector(".offline")?.textContent).toBe(UNREACHABLE);
  });
});

describe("track create", () => {
  function fill(form: HTMLFormElement, values: Record<string, string>) {
    for (const [name, value] of Object.entries(values)) {
      const input = form.querySelector<HTMLInputElement>(`input[name="${name}"]`);
      if (input) input.value = value;
    }
  }

  it("form: shows the labelled fields and the Create track and Cancel buttons", () => {
    const form = renderTrackCreate({ state: "form" }, { onCreate: vi.fn(), onCancel: vi.fn() });
    expect(Array.from(form.querySelectorAll("label")).map((l) => l.textContent)).toEqual([
      "Name",
      "Goal",
      "Deadline",
      "Time budget (optional)",
    ]);
    const buttons = Array.from(form.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons).toEqual(["Create track", "Cancel"]);
  });

  it("submit: sends the trimmed values and the budget as minutes", async () => {
    const onCreate = vi.fn(async () => undefined);
    const form = renderTrackCreate({ state: "form" }, { onCreate, onCancel: vi.fn() });
    document.body.append(form);
    fill(form as HTMLFormElement, { name: " Algebra ", goal: "Quadratics", deadline: "2026-12-31", minutes: "30" });
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(onCreate).toHaveBeenCalledOnce());
    expect(onCreate).toHaveBeenCalledWith({
      name: "Algebra",
      goal: "Quadratics",
      deadline: "2026-12-31",
      minutes: 30,
    });
  });

  it("submit: a blank name sends nothing", () => {
    const onCreate = vi.fn(async () => undefined);
    const form = renderTrackCreate({ state: "form" }, { onCreate, onCancel: vi.fn() });
    document.body.append(form);
    fill(form as HTMLFormElement, { name: "", deadline: "2026-12-31" });
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("submit: a blank deadline sends nothing", () => {
    const onCreate = vi.fn(async () => undefined);
    const form = renderTrackCreate({ state: "form" }, { onCreate, onCancel: vi.fn() });
    document.body.append(form);
    fill(form as HTMLFormElement, { name: "Algebra", deadline: "" });
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(onCreate).not.toHaveBeenCalled();
  });

  it.each(["0", "-1", "1.5", "abc"])("submit: a bad time budget %s sends nothing", (minutes) => {
    const onCreate = vi.fn(async () => undefined);
    const form = renderTrackCreate({ state: "form" }, { onCreate, onCancel: vi.fn() });
    document.body.append(form);
    fill(form as HTMLFormElement, { name: "Algebra", deadline: "2026-12-31", minutes });
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("submit: a failed save shows Could not create the track.", async () => {
    const onCreate = vi.fn(async () => {
      throw new Error("boom");
    });
    const form = renderTrackCreate({ state: "form" }, { onCreate, onCancel: vi.fn() });
    document.body.append(form);
    fill(form as HTMLFormElement, { name: "Algebra", deadline: "2026-12-31" });
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() =>
      expect(form.querySelector(".error")?.textContent).toBe("Could not create the track."),
    );
  });

  it("submit: an offline or timed-out save shows Server not reachable.", async () => {
    const onCreate = vi.fn(async () => {
      throw new CoreOfflineError("offline");
    });
    const form = renderTrackCreate({ state: "form" }, { onCreate, onCancel: vi.fn() });
    document.body.append(form);
    fill(form as HTMLFormElement, { name: "Algebra", deadline: "2026-12-31" });
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(form.querySelector(".error")?.textContent).toBe(UNREACHABLE));
    const timeout = vi.fn(async () => {
      throw new CoreTimeoutError("slow");
    });
    const second = renderTrackCreate({ state: "form" }, { onCreate: timeout, onCancel: vi.fn() });
    document.body.append(second);
    fill(second as HTMLFormElement, { name: "Algebra", deadline: "2026-12-31" });
    second.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(second.querySelector(".error")?.textContent).toBe(UNREACHABLE));
  });

  it("error state: shows Could not create the track. before any submit", () => {
    const form = renderTrackCreate({ state: "error" }, { onCreate: vi.fn(), onCancel: vi.fn() });
    expect(form.dataset.state).toBe("error");
    expect(form.querySelector(".error")?.textContent).toBe("Could not create the track.");
  });

  it("offline state: shows Server not reachable.", () => {
    const form = renderTrackCreate({ state: "offline" }, { onCreate: vi.fn(), onCancel: vi.fn() });
    expect(form.querySelector(".error")?.textContent).toBe(UNREACHABLE);
  });

  it("track create Cancel calls onCancel", () => {
    const onCancel = vi.fn();
    const form = renderTrackCreate({ state: "form" }, { onCreate: vi.fn(), onCancel });
    const cancel = Array.from(form.querySelectorAll<HTMLButtonElement>("button")).find(
      (b) => b.textContent === "Cancel",
    );
    cancel?.click();
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe("track detail", () => {
  it("ready: shows the name, goal, deadline, progress, velocity and sources", () => {
    const screen = renderTrackDetail({ state: "ready", track }, detailHandlers());
    expect(screen.querySelector(".name")?.textContent).toBe("Algebra");
    expect(screen.querySelector(".goal")?.textContent).toBe("Goal: Solve quadratics");
    expect(screen.querySelector(".deadline")?.textContent).toBe("Deadline: 2026-12-31");
    expect(screen.querySelector(".progress")?.textContent).toBe("Progress: 40%");
    expect(screen.querySelector(".velocity")?.textContent).toBe("Velocity: 2 concepts a week");
    expect(screen.querySelectorAll(".sources li")).toHaveLength(1);
    expect(screen.querySelector(".finish-early")).toBeNull();
    expect(screen.querySelector(".drop-reason")).toBeNull();
  });

  it("ready: shows the finish-early, too-slow and drop-reason notes when set", () => {
    const screen = renderTrackDetail(
      {
        state: "ready",
        track: {
          ...track,
          finishEarly: true,
          tooSlow: true,
          dropReason: "a new source added concepts",
        },
      },
      detailHandlers(),
    );
    expect(screen.querySelector(".finish-early")?.textContent).toBe(
      "Finish date: 3 weeks earlier than planned.",
    );
    expect(screen.querySelector(".too-slow")?.textContent).toBe("Too slow for the deadline.");
    expect(screen.querySelector(".drop-reason")?.textContent).toBe(
      "Progress dropped because a new source added concepts.",
    );
  });

  it("ready with no sources: shows This track has no sources yet.", () => {
    const screen = renderTrackDetail({ state: "ready", track: { ...track, sources: [] } }, detailHandlers());
    expect(screen.querySelector(".sources .empty")?.textContent).toBe("This track has no sources yet.");
  });

  it("empty and loading: no track body", () => {
    const empty = renderTrackDetail({ state: "empty", track: null }, detailHandlers());
    expect(empty.querySelector(".name")).toBeNull();
    const loading = renderTrackDetail({ state: "loading", track: null }, detailHandlers());
    expect(loading.getAttribute("aria-busy")).toBe("true");
    expect(loading.querySelector(".name")).toBeNull();
  });

  it("error: shows Could not load the track.", () => {
    const screen = renderTrackDetail({ state: "error", track: null }, detailHandlers());
    expect(screen.querySelector(".error")?.textContent).toBe("Could not load the track.");
  });

  it("track detail offline: shows Server not reachable.", () => {
    const screen = renderTrackDetail({ state: "offline", track: null }, detailHandlers());
    expect(screen.querySelector(".offline")?.textContent).toBe(UNREACHABLE);
  });

  it("Back, Add source and Quiz call their handlers", () => {
    const handlers = detailHandlers();
    const screen = renderTrackDetail({ state: "ready", track }, handlers);
    screen.querySelector<HTMLButtonElement>(".back")?.click();
    screen.querySelector<HTMLButtonElement>(".add-source")?.click();
    screen.querySelector<HTMLButtonElement>(".quiz")?.click();
    expect(handlers.onBack).toHaveBeenCalledOnce();
    expect(handlers.onAddSource).toHaveBeenCalledOnce();
    expect(handlers.onQuiz).toHaveBeenCalledOnce();
  });
});
