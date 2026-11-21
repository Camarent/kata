// Editor panel stub: one webview view with fixed text. The real panel comes in a later task.
import * as vscode from "vscode";

export const INFO_VIEW_ID = "kata.infoView";
export const INFO_TEXT = "Kata panel (stub)";

export function infoViewHtml(): string {
  return `<!DOCTYPE html><html><body>${INFO_TEXT}</body></html>`;
}

export function registerInfoView(): vscode.Disposable {
  return vscode.window.registerWebviewViewProvider(INFO_VIEW_ID, {
    resolveWebviewView(view) {
      view.webview.html = infoViewHtml();
    },
  });
}
