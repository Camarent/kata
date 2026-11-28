import { describe, expect, it } from "vitest";
import type { Backend } from "../src/backgroundBackend";
import { handlePanelMessage } from "../src/backgroundPanel";

describe("background panel handler", () => {
  it("replies with the not-available error for an image action, without calling the backend", async () => {
    const reply = await handlePanelMessage({} as Backend, { type: "panel:imageAction", label: "Explain" });
    expect(reply).toEqual({ ok: false, error: "image concepts are not available yet" });
  });
});
