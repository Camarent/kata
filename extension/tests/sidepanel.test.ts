import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderPanel, type PanelHandlers, type PanelRow, type PanelState } from "../src/sidepanel";

const session = { baseUrl: "http://localhost:8000", token: "t" };

function handlers(overrides: Partial<PanelHandlers> = {}): PanelHandlers {
  return {
    onSignIn: vi.fn(),
    onKnown: vi.fn(async () => "saved" as const),
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

  it("sends the sign-in values to onSignIn", () => {
    const h = handlers();
    renderPanel(root, { session: null, rows: [], status: { kind: "idle" } }, h);
    (root.querySelector('input[name="code"]') as HTMLInputElement).value = " 1234 ";
    (root.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = "laptop";
    root.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(h.onSignIn).toHaveBeenCalledWith({ code: "1234", deviceLabel: "laptop" });
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
    (root.querySelector('input[name="code"]') as HTMLInputElement).value = " 42 ";
    (root.querySelector('input[name="deviceLabel"]') as HTMLInputElement).value = " tab ";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(h.onSignIn).toHaveBeenCalledTimes(1);
    expect(h.onSignIn).toHaveBeenCalledWith({ code: "42", deviceLabel: "tab" });
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
});
