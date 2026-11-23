import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { host, resetHost } from "./mocks/vscode";
import { INFO_VIEW_ID, registerInfoView } from "../src/infoView";

beforeEach(() => {
  resetHost();
});

afterEach(() => {
  resetHost();
});

describe("registerInfoView", () => {
  it("registers one webview view provider under the info view id", () => {
    registerInfoView();

    expect([...host.webviewProviders.keys()]).toEqual([INFO_VIEW_ID]);
  });

  it("renders the static stub text into the view", () => {
    registerInfoView();
    const provider = host.webviewProviders.get(INFO_VIEW_ID);
    const view = { webview: { html: "" } };

    provider?.resolveWebviewView(view);

    expect(view.webview.html).toContain("Kata panel (stub)");
  });
});
