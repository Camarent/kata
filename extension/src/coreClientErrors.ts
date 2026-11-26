// Error classes of the core client. Every request maps its failures to one of these.
import type { ProgressDoc } from "./coreClientTypes";

/** The core did not answer within `timeoutMs`. */
export class CoreTimeoutError extends Error {
  constructor(message = "core did not answer in time") {
    super(message);
    this.name = "CoreTimeoutError";
  }
}

/** The core could not be reached (network failure). */
export class CoreOfflineError extends Error {
  constructor(message = "core is offline") {
    super(message);
    this.name = "CoreOfflineError";
  }
}

/** The core rejected the token or the enrolment code (HTTP 401). */
export class CoreAuthError extends Error {
  constructor(message = "core rejected the credentials") {
    super(message);
    this.name = "CoreAuthError";
  }
}

/** Any other non-2xx answer from the core. `code` is the stable `detail.code` of the body, when it has one. */
export class CoreHttpError extends Error {
  constructor(
    readonly status: number,
    readonly code?: string,
  ) {
    super(`core answered HTTP ${status}`);
    this.name = "CoreHttpError";
  }
}

/** A progress save lost the revision race (HTTP 412). Carries the stored revision and document. */
export class CoreConflictError extends Error {
  readonly status = 412;
  constructor(
    readonly revision: number,
    readonly doc: ProgressDoc | null,
  ) {
    super("progress revision moved; reload before saving");
    this.name = "CoreConflictError";
  }
}

/** The health probe got no answer from the address (network failure or timeout). */
export class CoreUnreachableError extends Error {
  constructor(message = "core is unreachable") {
    super(message);
    this.name = "CoreUnreachableError";
  }
}

/** The health probe got an answer that is not the kata health document. */
export class NotKataServerError extends Error {
  constructor(message = "address does not answer as a kata core") {
    super(message);
    this.name = "NotKataServerError";
  }
}
