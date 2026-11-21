// Extension entry: registers the install command, the info view, the quiet-mark diagnostics and
// the save poster. Settings are read on each save, so changes apply without a reload.
import * as vscode from "vscode";
import { readConfig } from "./config";
import { applyMessages } from "./diagnostics";
import { registerInfoView } from "./infoView";
import { installHooks } from "./installHooks";
import { postEvent } from "./poster";

export const INSTALL_COMMAND = "kata.installHooks";
export const SAVE_EVENT_NAME = "save";

export function activate(context: vscode.ExtensionContext): void {
  const diagnostics = vscode.languages.createDiagnosticCollection("kata");
  context.subscriptions.push(
    vscode.commands.registerCommand(INSTALL_COMMAND, () => runInstall()),
    registerInfoView(),
    diagnostics,
    vscode.workspace.onDidSaveTextDocument((doc) => postSave(doc, diagnostics)),
  );
}

export function deactivate(): void {
  // Nothing to release: every registration is disposed through context.subscriptions.
}

async function runInstall(): Promise<void> {
  const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (cwd === undefined) {
    await vscode.window.showInformationMessage("Kata: open a folder before installing hooks");
    return;
  }
  const result = await installHooks(cwd);
  const prefix = result.ok ? "Kata: hooks installed" : "Kata: hooks install failed";
  await vscode.window.showInformationMessage(`${prefix}: ${result.output}`);
}

// Posts one editor.save event for the saved document; the stop check runs inside postEvent.
async function postSave(doc: vscode.TextDocument, diagnostics: vscode.DiagnosticCollection): Promise<void> {
  const cfg = readConfig((key) => vscode.workspace.getConfiguration().get(key));
  const result = await postEvent(
    cfg,
    SAVE_EVENT_NAME,
    doc.languageId,
    new Date(),
    (input, init) => fetch(input, init),
    doc.getText(),
  );
  if (result.status === "posted") {
    applyMessages(diagnostics, doc.uri, result.messages);
  }
}
