// Shows a quiet mark from the server as one Information diagnostic on a document.
import * as vscode from "vscode";
import type { ServerMessage } from "./poster";

export const QUIET_MARK_MESSAGE = "Kata: quiet mark";

// Sets one quiet-mark diagnostic at line 0 when a quiet_mark message is present; clears the
// document's diagnostic when none is.
export function applyMessages(
  collection: vscode.DiagnosticCollection,
  uri: vscode.Uri,
  messages: ServerMessage[],
): void {
  if (messages.some((m) => m.kind === "quiet_mark")) {
    const range = new vscode.Range(0, 0, 0, 0);
    collection.set(uri, [
      new vscode.Diagnostic(range, QUIET_MARK_MESSAGE, vscode.DiagnosticSeverity.Information),
    ]);
  } else {
    collection.delete(uri);
  }
}
