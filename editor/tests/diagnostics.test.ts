import { describe, expect, it } from "vitest";
import * as vscode from "vscode";
import { applyMessages, QUIET_MARK_MESSAGE } from "../src/diagnostics";
import type { ServerMessage } from "../src/poster";

interface Call {
  op: "set" | "delete";
  uri: vscode.Uri;
  diagnostics?: readonly vscode.Diagnostic[];
}

function fakeCollection(): { collection: vscode.DiagnosticCollection; calls: Call[] } {
  const calls: Call[] = [];
  const collection: vscode.DiagnosticCollection = {
    set: (uri, diagnostics) => {
      calls.push({ op: "set", uri, diagnostics });
    },
    delete: (uri) => {
      calls.push({ op: "delete", uri });
    },
  };
  return { collection, calls };
}

const uri = { toString: () => "file:///doc.ts" } as vscode.Uri;

function message(kind: string): ServerMessage {
  return { id: 1, kind, body: { at: "2026-11-21T10:00:00Z", detail: {} }, created_at: "2026-11-21T10:00:01Z" };
}

describe("applyMessages", () => {
  it("sets one Information quiet-mark diagnostic at line 0 when a quiet_mark message arrives", () => {
    const { collection, calls } = fakeCollection();

    applyMessages(collection, uri, [message("nudge"), message("quiet_mark")]);

    expect(calls).toHaveLength(1);
    expect(calls[0].op).toBe("set");
    expect(calls[0].uri).toBe(uri);
    const diagnostics = calls[0].diagnostics ?? [];
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0].message).toBe(QUIET_MARK_MESSAGE);
    expect(diagnostics[0].message).toBe("Kata: quiet mark");
    expect(diagnostics[0].severity).toBe(vscode.DiagnosticSeverity.Information);
    expect(diagnostics[0].range.start.line).toBe(0);
  });

  it("clears the document diagnostic when no quiet_mark message is present", () => {
    const { collection, calls } = fakeCollection();

    applyMessages(collection, uri, [message("stop")]);
    applyMessages(collection, uri, []);

    expect(calls).toEqual([
      { op: "delete", uri },
      { op: "delete", uri },
    ]);
  });
});
