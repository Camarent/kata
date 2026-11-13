import { describe, expect, it } from "vitest";
import type { Block, Session } from "../src/types";

describe("test setup", () => {
  it("runs under jsdom", () => {
    expect(document).toBeDefined();
    expect(document.body).not.toBeNull();
  });

  it("exposes the shared types", () => {
    const block: Block = { id: "b1", text: "hello" };
    const session: Session = { baseUrl: "http://localhost", token: "x" };
    expect([block.id, session.token]).toHaveLength(2);
  });
});
