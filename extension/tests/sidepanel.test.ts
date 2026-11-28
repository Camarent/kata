import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderPanel, type PanelHandlers, type PanelRow, type PanelState } from "../src/sidepanel";
import { TEXT_COURSES_TAB, TEXT_SCAN_RESULTS } from "../src/ui/strings";

const session = { baseUrl: "http://localhost:8000", token: "t" };

function handlers(overrides: Partial<PanelHandlers> = {}): PanelHandlers {
  return {
    onTab: vi.fn(),
    onSignIn: vi.fn(),
    onDisconnect: vi.fn(),
    onChangeServer: vi.fn(),
    onCancelChange: vi.fn(),
    onKnown: vi.fn(async () => "saved" as const),
    onScan: vi.fn(async () => {}),
    onReview: vi.fn(async () => {}),
    onSetConcept: vi.fn(async () => {}),
    onCloseReview: vi.fn(),
    onOpenCourse: vi.fn(async () => {}),
    onDeleteCourse: vi.fn(async () => {}),
    onCreateCourse: vi.fn(async () => {}),
    onRegenerateCourse: vi.fn(async () => {}),
    onModelhost: vi.fn(async () => ({ ok: true, text: "done" })),
    ...overrides,
  };
}

function row(id: number, category: string, label: string, known: boolean | null): PanelRow {
  return { blockId: `b${id}`, topic: { id, category, label }, known };
}

describe("renderPanel", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("shows the sign-in form without a session", () => {
    const state: PanelState = { session: null, rows: [], status: { kind: "idle" } };
    renderPanel(root, state, handlers());
    expect(root.querySelector("form.signin")).not.toBeNull();
    expect(root.querySelector('input[name="code"]')).not.toBeNull();
    expect(root.querySelector('input[name="deviceLabel"]')).not.toBeNull();
    expect(root.querySelector("ul")).toBeNull();
  });

  it("first-run form has an empty server URL with the example placeholder and no default server", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
    const server = root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!;
    expect(server.value).toBe("");
    expect(server.placeholder).toBe("https://kata.example.org");
    expect(root.querySelector("button[type='submit']")?.textContent).toBe("Sign in");
    expect(root.querySelector("button")?.textContent).not.toBe("Cancel");
  });

  it("sends the sign-in values to onSignIn", () => {
    const h = handlers();
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
    (root.querySelector('input[name="baseUrl"]') as HTMLInputElement).value = " https://kata.example.org/ ";
    (root.querySelector('input[name="code"]') as HTMLInputElement).value = " 1234 ";
    (root.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = "laptop";
    root.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(h.onSignIn).toHaveBeenCalledWith({
      baseUrl: "https://kata.example.org/",
      code: "1234",
      deviceLabel: "laptop",
    });
  });

  it("does not sign in with an empty server URL and shows a message", () => {
    const h = handlers();
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
    (root.querySelector('input[name="code"]') as HTMLInputElement).value = "1234";
    (root.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = "laptop";
    root.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(h.onSignIn).not.toHaveBeenCalled();
    expect(root.querySelector("p.error")?.textContent).toBe("Enter the server URL");
  });

  it("connected view shows the session origin with Change server and Disconnect", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, h);
    expect(root.querySelector("form.signin")).toBeNull();
    expect(root.querySelector("p.origin")?.textContent).toBe("http://localhost:8000");
    root.querySelector<HTMLButtonElement>("button.change-server")!.click();
    expect(h.onChangeServer).toHaveBeenCalledTimes(1);
    root.querySelector<HTMLButtonElement>("button.disconnect")!.click();
    expect(h.onDisconnect).toHaveBeenCalledTimes(1);
  });

  it("changing server shows the form prefilled with the session URL and a Cancel button", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, changing: true }, h);
    expect(root.querySelector<HTMLInputElement>('input[name="baseUrl"]')!.value).toBe("http://localhost:8000");
    const cancel = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Cancel")!;
    cancel.click();
    expect(h.onCancelChange).toHaveBeenCalledTimes(1);
  });

  it("shows a notice on the status line", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "notice", text: "core is unreachable" } }, handlers());
    expect(root.querySelector("p.status")?.textContent).toBe("core is unreachable");
  });

  it("groups results by category", () => {
    const state: PanelState = {
      session,
      rows: [row(1, "greetings", "hola", false), row(2, "food", "pan", false), row(3, "greetings", "adios", true)],
      status: { kind: "idle" },
    };
    renderPanel(root, state, handlers());
    const headings = [...root.querySelectorAll("section.group h2")].map((h) => h.textContent);
    expect(headings).toEqual(["greetings", "food"]);
    const greetings = root.querySelectorAll("section.group")[0];
    expect([...greetings.querySelectorAll("span.label")].map((s) => s.textContent)).toEqual(["hola", "adios"]);
  });

  it("hides the button for known topics", () => {
    const state: PanelState = {
      session,
      rows: [row(1, "c", "known one", true), row(2, "c", "new one", false)],
      status: { kind: "idle" },
    };
    renderPanel(root, state, handlers());
    const buttons = [...root.querySelectorAll<HTMLButtonElement>("button")].filter(
      (b) => b.textContent === "I know this",
    );
    expect(buttons.map((b) => b.hidden)).toEqual([true, false]);
  });

  it("shows the status line for scanning, partial and error", () => {
    const status = (s: PanelState["status"]) => {
      renderPanel(root, { session, rows: [], status: s }, handlers());
      return root.querySelector("p.status")?.textContent;
    };
    expect(status({ kind: "scanning" })).toBe("scanning");
    expect(status({ kind: "partial", done: 2, total: 5 })).toBe("partial: 2 of 5");
    expect(status({ kind: "error", reason: "timeout" })).toBe("Core did not answer in time");
    expect(status({ kind: "error", reason: "auth" })).toBe("Sign-in failed or expired");
    expect(status({ kind: "error", reason: "failed" })).toBe("Something went wrong");
  });

  it("does not sign in with an empty code or device label and shows a message", () => {
    const h = handlers();
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
    const code = root.querySelector<HTMLInputElement>('input[name="code"]')!;
    const device = root.querySelector<HTMLInputElement>('input[name="deviceLabel"]')!;
    const form = root.querySelector("form")!;
    code.value = "   ";
    device.value = "laptop";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    code.value = "1234";
    device.value = "";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(h.onSignIn).not.toHaveBeenCalled();
    const errors = root.querySelectorAll("p.error");
    expect(errors).toHaveLength(1);
    expect(errors[0].textContent).toBe("Enter the code and a device label");
    expect(errors[0].getAttribute("role")).toBe("alert");
    expect(errors[0].closest("form")).toBe(form);
  });

  it("clears the message and signs in once when the form is filled", () => {
    const h = handlers();
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
    const form = root.querySelector("form")!;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    (root.querySelector('input[name="baseUrl"]') as HTMLInputElement).value = "https://kata.example.org";
    (root.querySelector('input[name="code"]') as HTMLInputElement).value = " 42 ";
    (root.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = " tab ";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(h.onSignIn).toHaveBeenCalledTimes(1);
    expect(h.onSignIn).toHaveBeenCalledWith({ baseUrl: "https://kata.example.org", code: "42", deviceLabel: "tab" });
    expect(root.querySelector("p.error")?.textContent).toBe("Signing in...");
  });

  it("signed out with error status shows the signed-out notice and the status line", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "error", reason: "auth" } }, handlers());
    expect(root.querySelector("div.signed-out")).not.toBeNull();
    expect(root.querySelector("form.signin")).toBeNull();
    expect(root.querySelector("p.status")?.textContent).toBe("Sign-in failed or expired");
  });

  it("signed out with idle status shows no status line", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("p.status")).toBeNull();
  });

  it("signed in with no rows and idle status shows the empty state", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("p.empty")?.textContent).toBe(TEXT_SCAN_RESULTS[27]);
    expect(root.querySelector("section.group")).toBeNull();
  });

  it("signed in with one row does not show the empty state", () => {
    renderPanel(root, { session, rows: [row(1, "c", "pan", false)], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("p.empty")).toBeNull();
    expect(root.querySelectorAll("section.group")).toHaveLength(1);
  });

  it("the scan screen lists both scan rows by label", () => {
    const rows = [row(1, "c", "pan", false), row(2, "c", "whisk", true)];
    renderPanel(root, { session, rows, status: { kind: "idle" } }, handlers());
    const labels = [...root.querySelectorAll("section.scan-results li.rrow span.nm")].map((node) => node.textContent);
    expect(labels).toEqual(["pan", "whisk"]);
  });

  it("calls onKnown once on click and shows queued text when offline", async () => {
    const h = handlers({ onKnown: vi.fn(async () => "queued" as const) });
    renderPanel(root, { session, rows: [row(7, "c", "pan", false)], status: { kind: "idle" } }, h);
    const button = [...root.querySelectorAll<HTMLButtonElement>("button")].find(
      (b) => b.textContent === "I know this",
    )!;
    button.click();
    await vi.waitFor(() => expect(root.querySelector("span.note")?.textContent).toBe("queued (offline)"));
    expect(h.onKnown).toHaveBeenCalledTimes(1);
    expect(h.onKnown).toHaveBeenCalledWith(7);
  });

  it("renders a hostile topic label as text (decoy)", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    renderPanel(
      root,
      { session, rows: [row(9, "c", hostile, false)], status: { kind: "idle" } },
      handlers(),
    );
    const label = root.querySelector("span.label")!;
    expect(label.textContent).toBe(hostile);
    expect(root.querySelector("img")).toBeNull();
  });

  it("shows the tab bar and the Scan page button only in the connected view", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("button.scan-page")).toBeNull();
    expect(root.querySelector("nav.tabs")).toBeNull();
    renderPanel(root, { session: session, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("button.scan-page")?.textContent).toBe(TEXT_SCAN_RESULTS[1]);
    expect([...root.querySelectorAll("nav.tabs button")].map((b) => b.textContent)).toEqual([
      // Literal labels: a reorder of the inventory must fail here, not rename a tab silently.
      "Scan results",
      "Review",
      "Courses",
      "Tracks",
      "Settings",
    ]);
    expect(root.querySelector("nav.tabs button[aria-current]")?.classList.contains("tab-scan")).toBe(true);
  });

  it("calls onScan when Scan page is clicked", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, h);
    root.querySelector<HTMLButtonElement>("button.scan-page")!.click();
    expect(h.onScan).toHaveBeenCalledTimes(1);
  });

  it("disables Scan page while a scan is in flight", () => {
    renderPanel(root, { session, rows: [], status: { kind: "scanning" } }, handlers());
    expect(root.querySelector<HTMLButtonElement>("button.scan-page")?.disabled).toBe(true);
    expect(root.querySelector("p.status")?.textContent).toBe("scanning");
  });

  it("calls onTab with the tab of the clicked tab button", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, h);
    for (const tab of ["review", "courses", "tracks", "settings", "scan"]) {
      root.querySelector<HTMLButtonElement>(`nav.tabs button.tab-${tab}`)!.click();
      expect(h.onTab).toHaveBeenLastCalledWith(tab);
    }
    expect(h.onTab).toHaveBeenCalledTimes(5);
  });

  it("draws the review rows when state.review is set and marks the Review tab", () => {
    const state: PanelState = {
      session,
      rows: [row(1, "greetings", "hola", false)],
      status: { kind: "idle" },
      review: [
        { conceptId: 5, label: "ser", state: null, evidence: "" },
        { conceptId: 6, label: "estar", state: "known", evidence: "" },
      ],
    };
    renderPanel(root, state, handlers());
    expect([...root.querySelectorAll("li.review-row span.label")].map((s) => s.textContent)).toEqual([
      "ser",
      "estar",
    ]);
    expect(root.querySelector("section.group")).toBeNull();
    expect(root.querySelector("button.scan-page")).toBeNull();
    expect(root.querySelector("nav.tabs button[aria-current]")?.classList.contains("tab-review")).toBe(true);
  });

  it("sends the chosen state to onSetConcept from a review row", async () => {
    const h = handlers();
    const state: PanelState = {
      session,
      rows: [],
      status: { kind: "idle" },
      review: [{ conceptId: 5, label: "ser", state: null, evidence: "" }],
    };
    renderPanel(root, state, h);
    const learning = [...root.querySelectorAll<HTMLButtonElement>("button.state-button")].find(
      (b) => b.textContent === "Learning",
    )!;
    learning.click();
    await vi.waitFor(() => expect(h.onSetConcept).toHaveBeenCalledTimes(1));
    expect(h.onSetConcept).toHaveBeenCalledWith(5, "learning");
  });

  it("draws the screen of the stored tab: courses, tracks, settings", () => {
    const base = { session, rows: [], status: { kind: "idle" } } as const;
    renderPanel(root, { ...base, tab: "courses" }, handlers());
    expect(root.querySelector("section.courses-tab")).not.toBeNull();
    renderPanel(root, { ...base, tab: "tracks" }, handlers());
    expect(root.querySelector("section.tracks-tab")).not.toBeNull();
    renderPanel(root, { ...base, tab: "settings" }, handlers());
    expect(root.querySelector("section.settings-home")).not.toBeNull();
    expect(root.querySelector("section.local-model")).not.toBeNull();
    expect(root.querySelector("button.scan-page")).toBeNull();
  });

  const courses = [
    { id: 4, title: "Algebra" },
    { id: 9, title: "Biology" },
  ];
  const coursesState = (extra: Partial<PanelState> = {}): PanelState => ({
    session,
    rows: [],
    status: { kind: "idle" },
    tab: "courses",
    courses,
    ...extra,
  });

  it("draws one Open course and Delete button per ready course on the Courses tab", () => {
    renderPanel(root, coursesState(), handlers());
    const tab = root.querySelector("section.courses-tab")!;
    expect([...tab.querySelectorAll("li span:first-child")].map((s) => s.textContent)).toEqual(["Algebra", "Biology"]);
    expect([...tab.querySelectorAll("li button")].map((b) => b.textContent)).toEqual([
      TEXT_COURSES_TAB[5],
      TEXT_COURSES_TAB[25],
      TEXT_COURSES_TAB[5],
      TEXT_COURSES_TAB[25],
    ]);
  });

  it("shows the empty text with no courses and the could-not-load text after a failed load", () => {
    renderPanel(root, coursesState({ courses: [] }), handlers());
    expect(root.querySelector("section.courses-tab p.empty")?.textContent).toBe(TEXT_COURSES_TAB[3]);
    renderPanel(root, coursesState({ coursesFailed: true }), handlers());
    expect(root.querySelector("section.courses-tab p.error")?.textContent).toBe(TEXT_COURSES_TAB[23]);
  });

  it("turns Generate course off while the server is down", () => {
    renderPanel(root, coursesState({ link: { serverUp: false, unsynced: 0 } }), handlers());
    const generate = [...root.querySelectorAll<HTMLButtonElement>("section.courses-tab button")].find(
      (b) => b.textContent === TEXT_COURSES_TAB[8],
    )!;
    expect(generate.disabled).toBe(true);
  });

  describe("local model section", () => {
    const modelText = (): string | null | undefined => root.querySelector("section.local-model p.modelhost-text")?.textContent;
    const modelRows = (): string[] =>
      [...root.querySelectorAll("section.local-model li.model")].map((li) => li.textContent ?? "");
    const modelButton = (className: string): HTMLButtonElement =>
      root.querySelector<HTMLButtonElement>(`section.local-model button.${className}`)!;
    const draw = (h: PanelHandlers): void =>
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, tab: "settings", courses }, h);
    it.each([
      ["modelhost-start", "Start", { action: "start" }],
      ["modelhost-measure", "Measure", { action: "measure" }],
      ["modelhost-status", "Status", { action: "status" }],
    ])("runs the %s button as a %s request", async (className, label, request) => {
      const h = handlers();
      draw(h);
      expect(modelButton(className).textContent).toBe(label);
      modelButton(className).click();
      expect(h.onModelhost).toHaveBeenCalledWith(request);
      await vi.waitFor(() => expect(modelText()).toBe("done"));
    });

    it("sends the chosen engine with Use engine", async () => {
      const h = handlers();
      draw(h);
      expect(modelButton("modelhost-use").textContent).toBe("Use engine");
      const engine = root.querySelector<HTMLSelectElement>("section.local-model select")!;
      expect([...engine.options].map((option) => option.value)).toEqual(["ollama", "strata", "none"]);
      engine.value = "strata";
      modelButton("modelhost-use").click();
      expect(h.onModelhost).toHaveBeenCalledWith({ action: "use", engine: "strata" });
      await vi.waitFor(() => expect(modelText()).toBe("done"));
    });

    it("disables the buttons while a job runs", async () => {
      let finish = (): void => {};
      const h = handlers({
        onModelhost: vi.fn(() => new Promise<{ ok: boolean; text: string }>((resolve) => (finish = () => resolve({ ok: true, text: "done" })))),
      });
      draw(h);
      modelButton("modelhost-start").click();
      expect(modelButton("modelhost-start").disabled).toBe(true);
      expect(modelButton("modelhost-use").disabled).toBe(true);
      finish();
      await vi.waitFor(() => expect(modelButton("modelhost-start").disabled).toBe(false));
    });

    it("shows the waiting text when the job is still pending after the timeout", async () => {
      const h = handlers({ onModelhost: vi.fn(async () => "pending" as const) });
      draw(h);
      modelButton("modelhost-measure").click();
      await vi.waitFor(() => expect(modelText()).toBe("waiting for the PC worker"));
    });

    it("shows each model's fits, with null shown as unknown", async () => {
      const capabilities = {
        models: {
          qwen: { fits_alone: true, fits_together: null },
          llama: { fits_alone: false, fits_together: false },
          mini: {},
        },
      };
      const h = handlers({ onModelhost: vi.fn(async () => ({ ok: true, text: "measured", capabilities })) });
      draw(h);
      modelButton("modelhost-measure").click();
      await vi.waitFor(() => expect(modelRows()).toHaveLength(3));
      expect(modelText()).toBe("measured");
      expect(modelRows()).toEqual([
        "qwen: alone fits, together unknown",
        "llama: alone does not fit, together does not fit",
        "mini: alone unknown, together unknown",
      ]);
    });

    it("shows the error text when the job fails", async () => {
      const h = handlers({ onModelhost: vi.fn(async () => Promise.reject(new Error("modelhost job 7 failed"))) });
      draw(h);
      modelButton("modelhost-status").click();
      await vi.waitFor(() => expect(modelText()).toBe("modelhost job 7 failed"));
      expect(modelButton("modelhost-status").disabled).toBe(false);
    });
  });

  const tabButton = (course: string, label: string): HTMLButtonElement => {
    const item = [...root.querySelectorAll("section.courses-tab li")].find(
      (li) => li.querySelector("span")?.textContent === course,
    )!;
    return [...item.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === label)!;
  };

  it("calls onOpenCourse with the course id when Open course is clicked", () => {
    const h = handlers();
    renderPanel(root, coursesState(), h);
    tabButton("Biology", TEXT_COURSES_TAB[5]).click();
    expect(h.onOpenCourse).toHaveBeenCalledTimes(1);
    expect(h.onOpenCourse).toHaveBeenCalledWith(9);
  });

  it("Delete asks first, Cancel keeps the course and Confirm calls onDeleteCourse with its id", async () => {
    const h = handlers();
    renderPanel(root, coursesState(), h);
    tabButton("Algebra", TEXT_COURSES_TAB[25]).click();
    expect(h.onDeleteCourse).not.toHaveBeenCalled();
    root.querySelector<HTMLButtonElement>("button.confirm-no")!.click();
    await Promise.resolve();
    expect(h.onDeleteCourse).not.toHaveBeenCalled();
    tabButton("Algebra", TEXT_COURSES_TAB[25]).click();
    root.querySelector<HTMLButtonElement>("button.confirm-yes")!.click();
    await vi.waitFor(() => expect(h.onDeleteCourse).toHaveBeenCalledTimes(1));
    expect(h.onDeleteCourse).toHaveBeenCalledWith(4);
  });

  it("shows the delete-failed text when onDeleteCourse rejects", async () => {
    const h = handlers({ onDeleteCourse: vi.fn(async () => Promise.reject(new Error("delete refused"))) });
    renderPanel(root, coursesState(), h);
    tabButton("Biology", TEXT_COURSES_TAB[25]).click();
    root.querySelector<HTMLButtonElement>("button.confirm-yes")!.click();
    await vi.waitFor(() => expect(root.querySelector("section.courses-tab p.error")?.textContent).toBe(TEXT_COURSES_TAB[28]));
  });
});
