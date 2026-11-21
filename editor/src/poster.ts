// Posts one editor event to POST /v1/events (docs/api.md:54-74). The event carries the language
// only, never document text. Text is read here only to test the local stop patterns.
import type { KataConfig } from "./config";
import { matchesStop } from "./stopPatterns";

export type FetchFn = (input: string, init: RequestInit) => Promise<Response>;

// A message piggybacked on the response (docs/api.md:74).
export interface ServerMessage {
  id: number;
  kind: string;
  body: { at: string; detail: object };
  created_at: string;
}

export type PostResult =
  | { status: "posted"; messages: ServerMessage[] }
  | { status: "skipped" }
  | { status: "error"; reason: string };

// Posts `editor.<name>` unless a stop pattern matches `documentText`. Never throws: a network
// failure or a non-200 answer returns status "error".
export async function postEvent(
  cfg: KataConfig,
  name: string,
  language: string,
  now: Date,
  fetchFn: FetchFn,
  documentText: string,
): Promise<PostResult> {
  if (matchesStop(documentText, cfg.stopPatterns)) {
    return { status: "skipped" };
  }
  const event = {
    event_id: crypto.randomUUID(),
    type: `editor.${name}`,
    occurred_at: now.toISOString(),
    payload: { language },
  };
  let response: Response;
  try {
    response = await fetchFn(`${cfg.serverUrl}/v1/events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${cfg.token}`,
      },
      body: JSON.stringify({ events: [event] }),
    });
  } catch (err) {
    return { status: "error", reason: err instanceof Error ? err.message : String(err) };
  }
  if (response.status !== 200) {
    return { status: "error", reason: `HTTP ${response.status}` };
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { status: "error", reason: "response is not JSON" };
  }
  const messages = (body as { messages?: unknown } | null)?.messages;
  return { status: "posted", messages: Array.isArray(messages) ? (messages as ServerMessage[]) : [] };
}
