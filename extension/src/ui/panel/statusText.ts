// Text of the panel status line. The inventory (ui/strings.ts) has no entry for these lines.

/** Reason a scan or panel call failed. */
export type ErrorReason = "timeout" | "auth" | "failed";

/** User-facing text for each error reason. */
export const ERROR_TEXT: Record<ErrorReason, string> = {
  timeout: "Core did not answer in time",
  auth: "Sign-in failed or expired",
  failed: "Something went wrong",
};

/** Status line text while a scan runs. */
export const SCANNING_TEXT = "scanning";

/** Status line text for a scan that returned part of its blocks. */
export function partialText(done: number, total: number): string {
  return `partial: ${done} of ${total}`;
}
