/** Settings of the extension. The only place these literals live. */

/** Longest a single core request may take, in milliseconds. */
export const REQUEST_TIMEOUT_MS = 5000;

/** Delay between two job status polls, in milliseconds. */
export const POLL_MS = 500;

/** Time after which an unfinished tagging job counts as timed out, in milliseconds. */
export const MAX_WAIT_MS = 30000;
