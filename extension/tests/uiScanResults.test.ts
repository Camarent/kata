import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PanelHandlers } from "../src/sidepanel";
import { renderScanResults, type ScanResultRow } from "../src/ui/panel/scanResults";
import { renderSummaryPanel, type SummaryTopicView } from "../src/ui/panel/summaryPanel";
import { PANEL_CSS } from "../src/ui/panelCss";
import { TEXT_CONN_DETAIL, TEXT_SCAN_RESULTS, TEXT_SUMMARY_PANEL } from "../src/ui/strings";

const LONG_LABEL =
  "Transmission control protocol three-way handshake with synchronise and acknowledge packets, retransmission timers and congestion window growth";

const ROWS: ScanResultRow[] = [
  { label: "TCP handshake", state: "known" },
  { label: LONG_LABEL, state: "learning" },
  { label: "Subnet mask", state: "new" },
];

const TOPICS: SummaryTopicView[] = [
  { name: "Networking basics", conceptCount: 4 },
  { name: LONG_LABEL, conceptCount: 2 },
];

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

/** Button with the given visible text inside root; fails the test when there is none. */
function buttonNamed(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === text);
  if (found === undefined) throw new Error(`no button "${text}"`);
  return found;
}

describe("scan results screen", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("title and Scan page button, then the empty text when no scan yet", () => {
    const h = handlers();
    root.append(renderScanResults({ status: "empty", rows: [] }, h));
    expect(root.querySelector("h2")?.textContent).toBe(TEXT_SCAN_RESULTS[0]);
    expect(root.querySelector(".empty")?.textContent).toBe(TEXT_SCAN_RESULTS[27]);
    expect(root.querySelector("ul")).toBeNull();
    buttonNamed(root, TEXT_SCAN_RESULTS[1]).click();
    expect(h.onScan).toHaveBeenCalledOnce();
  });

  it("loading shows Scanning...", () => {
    root.append(renderScanResults({ status: "loading", rows: [] }, handlers()));
    expect(root.querySelector(".loading")?.textContent).toBe(TEXT_SCAN_RESULTS[28]);
  });

  it("error shows the scan failure text in the error banner", () => {
    root.append(renderScanResults({ status: "error", rows: [] }, handlers()));
    const banner = root.querySelector(".banner.err");
    expect(banner?.textContent).toBe(TEXT_SCAN_RESULTS[29]);
  });

  it("offline shows the server-down text in the warn banner", () => {
    root.append(renderScanResults({ status: "offline", rows: [] }, handlers()));
    expect(root.querySelector(".banner.warn")?.textContent).toBe(TEXT_SCAN_RESULTS[30]);
  });

  it("ready lists one row per concept with its state badge", () => {
    root.append(renderScanResults({ status: "ready", rows: ROWS }, handlers()));
    const rows = [...root.querySelectorAll("li.rrow")];
    expect(rows).toHaveLength(3);
    expect(rows[0]?.querySelector(".badge")?.textContent).toBe(TEXT_SCAN_RESULTS[15]);
    expect(rows[1]?.querySelector(".badge")?.textContent).toBe(TEXT_SCAN_RESULTS[16]);
    expect(rows[2]?.querySelector(".badge")?.textContent).toBe(TEXT_SCAN_RESULTS[17]);
  });

  it("long labels keep their full text and carry the clamp2 class", () => {
    root.append(renderScanResults({ status: "ready", rows: ROWS }, handlers()));
    const labels = [...root.querySelectorAll<HTMLElement>(".nm")];
    expect(labels.every((node) => node.classList.contains("clamp2"))).toBe(true);
    expect(labels[1]?.textContent).toBe(LONG_LABEL);
  });

  it("clamp2 is a two-line clamp in the panel stylesheet", () => {
    expect(PANEL_CSS).toMatch(/\.clamp2\s*\{[^}]*-webkit-line-clamp:\s*2;/);
  });
});

describe("summary panel screen", () => {
  let root: HTMLElement;

  beforeEach(() => {
    root = document.createElement("main");
    document.body.append(root);
  });

  afterEach(() => {
    root.remove();
  });

  it("title and page text summary heading always show", () => {
    root.append(renderSummaryPanel({ status: "empty", topics: [] }));
    expect(root.querySelector("h2")?.textContent).toBe(TEXT_SUMMARY_PANEL[0]);
    expect(root.querySelector("h3")?.textContent).toBe(TEXT_SUMMARY_PANEL[1]);
  });

  it("empty asks for a scan first and lists no topics", () => {
    root.append(renderSummaryPanel({ status: "empty", topics: [] }));
    expect(root.querySelector(".empty")?.textContent).toBe(TEXT_SUMMARY_PANEL[4]);
    expect(root.querySelector("ul")).toBeNull();
  });

  it("loading shows the writing text", () => {
    root.append(renderSummaryPanel({ status: "loading", topics: [] }));
    expect(root.querySelector(".loading")?.textContent).toBe(TEXT_SUMMARY_PANEL[5]);
  });

  it("error shows the write-failure text in the error banner", () => {
    root.append(renderSummaryPanel({ status: "error", topics: [] }));
    expect(root.querySelector(".banner.err")?.textContent).toBe(TEXT_SUMMARY_PANEL[6]);
  });

  it("offline shows the server-down text in the warn banner", () => {
    root.append(renderSummaryPanel({ status: "offline", topics: [] }));
    expect(root.querySelector(".banner.warn")?.textContent).toBe(TEXT_CONN_DETAIL[2]);
  });

  it("ready lists each topic with its concept count and the long name clamped", () => {
    root.append(renderSummaryPanel({ status: "ready", topics: TOPICS, onAddTopic: vi.fn() }));
    const rows = [...root.querySelectorAll("li.rrow")];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.querySelector(".cnt")?.textContent).toBe("4");
    expect(rows[1]?.querySelector(".nm")?.textContent).toBe(LONG_LABEL);
    expect(rows[1]?.querySelector(".nm")?.classList.contains("clamp2")).toBe(true);
  });

  it("Add all concepts of topic passes the topic name", () => {
    const onAddTopic = vi.fn();
    root.append(renderSummaryPanel({ status: "ready", topics: TOPICS, onAddTopic }));
    buttonNamed(root, TEXT_SUMMARY_PANEL[8]).click();
    expect(onAddTopic).toHaveBeenCalledWith("Networking basics");
  });

  it("Back to scan results calls onBack when present, hidden otherwise", () => {
    const onBack = vi.fn();
    root.append(renderSummaryPanel({ status: "empty", topics: [], onBack }));
    buttonNamed(root, TEXT_SUMMARY_PANEL[7]).click();
    expect(onBack).toHaveBeenCalledOnce();
    root.replaceChildren(renderSummaryPanel({ status: "empty", topics: [] }));
    expect(root.querySelector(".back")).toBeNull();
  });
});
