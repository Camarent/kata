import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoreHttpError } from "../src/coreClient";
import { renderPanel, type PanelHandlers, type PanelRow, type PanelState } from "../src/sidepanel";

const session = { baseUrl: "http://localhost:8000", token: "t" };

function handlers(overrides: Partial<PanelHandlers> = {}): PanelHandlers {
  return {
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
    expect(root.querySelector("button[type='submit']")?.textContent).toBe("Connect");
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
    expect(root.querySelector("p.error")?.textContent).toBe("");
  });

  it("signed out with error status shows the status line", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "error", reason: "auth" } }, handlers());
    expect(root.querySelector("form.signin")).not.toBeNull();
    expect(root.querySelector("p.status")?.textContent).toBe("Sign-in failed or expired");
  });

  it("signed out with idle status shows no status line", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("p.status")).toBeNull();
  });

  it("signed in with no rows and idle status shows the empty state", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("p.empty")?.textContent).toBe("Nothing scanned yet");
    expect(root.querySelector("section.group")).toBeNull();
  });

  it("signed in with one row does not show the empty state", () => {
    renderPanel(root, { session, rows: [row(1, "c", "pan", false)], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("p.empty")).toBeNull();
    expect(root.querySelectorAll("section.group")).toHaveLength(1);
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

  it("shows the Scan this page button only in the connected view", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("button.scan")).toBeNull();
    renderPanel(root, { session: session, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("button.scan")?.textContent).toBe("Scan this page");
    renderPanel(root, { session: session, rows: [], status: { kind: "idle" }, review: [] }, handlers());
    expect(root.querySelector("button.scan")).toBeNull();
  });

  it("calls onScan when Scan this page is clicked", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, h);
    root.querySelector<HTMLButtonElement>("button.scan")!.click();
    expect(h.onScan).toHaveBeenCalledTimes(1);
  });

  it("disables Scan this page while a scan is in flight", () => {
    renderPanel(root, { session, rows: [], status: { kind: "scanning" } }, handlers());
    expect(root.querySelector<HTMLButtonElement>("button.scan")?.disabled).toBe(true);
    expect(root.querySelector("p.status")?.textContent).toBe("scanning");
  });

  it("shows the Review concepts button only when signed in", () => {
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, handlers());
    expect(root.querySelector("button.review-open")).toBeNull();
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, handlers());
    const button = root.querySelector<HTMLButtonElement>("button.review-open");
    expect(button?.textContent).toBe("Review concepts");
  });

  it("calls onReview when the Review concepts button is clicked", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" } }, h);
    root.querySelector<HTMLButtonElement>("button.review-open")!.click();
    expect(h.onReview).toHaveBeenCalledTimes(1);
  });

  it("draws the review rows instead of the scan view when state.review is set", () => {
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
    expect(root.querySelector("button.review-open")).toBeNull();
    expect(root.querySelector("button.back")?.textContent).toBe("Back");
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
      (b) => b.textContent === "learning",
    )!;
    learning.click();
    await vi.waitFor(() => expect(h.onSetConcept).toHaveBeenCalledTimes(1));
    expect(h.onSetConcept).toHaveBeenCalledWith(5, "learning");
  });

  it("Back calls onCloseReview and the scan view returns once review is cleared", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, review: [] }, h);
    root.querySelector<HTMLButtonElement>("button.back")!.click();
    expect(h.onCloseReview).toHaveBeenCalledTimes(1);
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, review: null }, h);
    expect(root.querySelector("button.review-open")).not.toBeNull();
    expect(root.querySelector("button.back")).toBeNull();
  });

  const courses = [
    { id: 4, title: "Algebra" },
    { id: 9, title: "Biology" },
  ];

  it("draws a Courses section with one Open course button per ready course", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, handlers());
    const section = root.querySelector("section.courses")!;
    expect(section.querySelector("h2")?.textContent).toBe("Courses");
    const buttons = [...section.querySelectorAll<HTMLButtonElement>("ul button")].filter((b) => !b.hidden);
    expect(buttons.map((b) => b.textContent)).toEqual(["Open course", "Delete", "Open course", "Delete"]);
    expect([...section.querySelectorAll(".course-title")].map((s) => s.textContent)).toEqual(["Algebra", "Biology"]);
  });

  it("keeps the Courses section with the create form when there are no ready courses", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses: [] }, handlers());
    expect(root.querySelector("section.courses form.create-course")).not.toBeNull();
    expect(root.querySelector("section.courses ul")?.children.length).toBe(0);
  });

  describe("create course form", () => {
    function submitTitle(value: string): void {
      (root.querySelector('input[name="courseTitle"]') as HTMLInputElement).value = value;
      root.querySelector("form.create-course")!.dispatchEvent(new Event("submit", { cancelable: true }));
    }
    const courseNote = (): string | null | undefined => root.querySelector("form.create-course p.course-note")?.textContent;

    it("labels the title input and names the button Create course", () => {
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, handlers());
      const input = root.querySelector<HTMLInputElement>('form.create-course input[name="courseTitle"]')!;
      expect(root.querySelector("form.create-course label")?.textContent).toBe("New course title");
      expect(input.closest("label")).not.toBeNull();
      expect(root.querySelector("form.create-course button")?.textContent).toBe("Create course");
    });

    it("calls onCreateCourse with the trimmed title and clears the input", async () => {
      const h = handlers();
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
      submitTitle("  Chemistry  ");
      expect(h.onCreateCourse).toHaveBeenCalledWith("Chemistry");
      expect((root.querySelector('input[name="courseTitle"]') as HTMLInputElement).value).toBe("");
      await vi.waitFor(() => expect(root.querySelector<HTMLButtonElement>("form.create-course button")?.disabled).toBe(false));
      expect(courseNote()).toBe("");
    });

    it("does not call onCreateCourse for a blank title", () => {
      const h = handlers();
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
      submitTitle("   ");
      expect(h.onCreateCourse).not.toHaveBeenCalled();
    });

    it("disables the Create button while the create runs", async () => {
      let finish = (): void => {};
      const h = handlers({ onCreateCourse: vi.fn(() => new Promise<void>((resolve) => (finish = resolve))) });
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
      submitTitle("Chemistry");
      expect(root.querySelector<HTMLButtonElement>("form.create-course button")?.disabled).toBe(true);
      finish();
      await vi.waitFor(() => expect(root.querySelector<HTMLButtonElement>("form.create-course button")?.disabled).toBe(false));
    });

    it.each([
      ["course_limit", "You have reached your course limit. Delete a course to add another."],
      ["course_name_taken", "A course with this name already exists. Choose another title."],
      ["course_title_empty", "Enter a course title."],
    ])("shows the text for %s in the create note", async (code, text) => {
      const h = handlers({ onCreateCourse: vi.fn(async () => Promise.reject(new CoreHttpError(409, code))) });
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
      submitTitle("Chemistry");
      await vi.waitFor(() => expect(courseNote()).toBe(text));
      expect(root.querySelector<HTMLButtonElement>("form.create-course button")?.disabled).toBe(false);
    });

    it("shows the generic text for any other create failure", async () => {
      const h = handlers({ onCreateCourse: vi.fn(async () => Promise.reject(new Error("offline"))) });
      renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
      submitTitle("Chemistry");
      await vi.waitFor(() => expect(courseNote()).toBe("Could not save the course. Try again."));
    });
  });

  describe("local model section", () => {
    const modelText = (): string | null | undefined => root.querySelector("section.local-model p.modelhost-text")?.textContent;
    const modelRows = (): string[] =>
      [...root.querySelectorAll("section.local-model li.model")].map((li) => li.textContent ?? "");
    const modelButton = (className: string): HTMLButtonElement =>
      root.querySelector<HTMLButtonElement>(`section.local-model button.${className}`)!;
    const draw = (h: PanelHandlers): void => renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);

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

  it("calls onOpenCourse with the course id and disables the button on click", async () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
    const second = [...root.querySelectorAll<HTMLButtonElement>("section.courses button")].find(
      (b) => b.getAttribute("aria-label") === "Open Biology",
    )!;
    second.click();
    expect(second.disabled).toBe(true);
    await vi.waitFor(() => expect(root.querySelectorAll("section.courses span.note")[1]?.textContent).toBe("opened"));
    expect(h.onOpenCourse).toHaveBeenCalledTimes(1);
    expect(h.onOpenCourse).toHaveBeenCalledWith(9);
  });

  it("shows the error text and re-enables the button when opening fails", async () => {
    const h = handlers({ onOpenCourse: vi.fn(async () => Promise.reject(new Error("course is not ready"))) });
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
    const first = root.querySelector<HTMLButtonElement>("section.courses button")!;
    first.click();
    await vi.waitFor(() => expect(root.querySelector("section.courses span.note")?.textContent).toBe("course is not ready"));
    expect(first.disabled).toBe(false);
    expect(h.onOpenCourse).toHaveBeenCalledWith(4);
  });

  const deleteButton = (name: string) =>
    root.querySelector<HTMLButtonElement>(`section.courses button[aria-label="Delete ${name}"]`)!;
  const labelled = (label: string) => root.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;

  it("first Delete click asks to confirm without calling onDeleteCourse", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
    deleteButton("Biology").click();
    expect(deleteButton("Biology").hidden).toBe(true);
    expect(labelled("Confirm delete of Biology").hidden).toBe(false);
    expect(labelled("Confirm delete of Biology").textContent).toBe("Confirm delete");
    expect(labelled("Cancel delete of Biology").hidden).toBe(false);
    expect(labelled("Cancel delete of Biology").textContent).toBe("Cancel");
    expect(h.onDeleteCourse).not.toHaveBeenCalled();
  });

  it("Cancel restores the Delete button without calling onDeleteCourse", () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
    deleteButton("Biology").click();
    labelled("Cancel delete of Biology").click();
    expect(deleteButton("Biology").hidden).toBe(false);
    expect(labelled("Confirm delete of Biology").hidden).toBe(true);
    expect(labelled("Cancel delete of Biology").hidden).toBe(true);
    expect(h.onDeleteCourse).not.toHaveBeenCalled();
  });

  it("Confirm delete calls onDeleteCourse with the course id", async () => {
    const h = handlers();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
    deleteButton("Algebra").click();
    labelled("Confirm delete of Algebra").click();
    await vi.waitFor(() => expect(h.onDeleteCourse).toHaveBeenCalledTimes(1));
    expect(h.onDeleteCourse).toHaveBeenCalledWith(4);
  });

  it("shows the delete error in the course note and restores the Delete button", async () => {
    const h = handlers({ onDeleteCourse: vi.fn(async () => Promise.reject(new Error("delete refused"))) });
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, h);
    deleteButton("Biology").click();
    labelled("Confirm delete of Biology").click();
    await vi.waitFor(() => expect(root.querySelectorAll("section.courses span.note")[1]?.textContent).toBe("delete refused"));
    expect(deleteButton("Biology").hidden).toBe(false);
    expect(labelled("Confirm delete of Biology").hidden).toBe(true);
    expect(labelled("Confirm delete of Biology").disabled).toBe(false);
  });

  it("shows n of limit when the course limit is above 0", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses, courseLimit: 5, courseTotal: 2 }, handlers());
    expect(root.querySelector("section.courses p.course-limit")?.textContent).toBe("2 of 5");
  });

  it("counts the listed courses when courseTotal is absent", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses, courseLimit: 5 }, handlers());
    expect(root.querySelector("section.courses p.course-limit")?.textContent).toBe("2 of 5");
  });

  it("shows no limit text when the course limit is 0 or absent", () => {
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses, courseLimit: 0 }, handlers());
    expect(root.querySelector("p.course-limit")).toBeNull();
    renderPanel(root, { session, rows: [], status: { kind: "idle" }, courses }, handlers());
    expect(root.querySelector("p.course-limit")).toBeNull();
  });
});
