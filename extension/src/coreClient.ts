/** HTTP client for the local kata core: enrol, jobs, marks. Every call has a timeout. */

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

/** Any other non-2xx answer from the core. */
export class CoreHttpError extends Error {
  constructor(readonly status: number) {
    super(`core answered HTTP ${status}`);
    this.name = "CoreHttpError";
  }
}

export interface CoreClientOptions {
  baseUrl: string;
  token?: string;
  timeoutMs: number;
  fetchImpl?: typeof fetch;
}

/** Answer of `GET /jobs/{id}`. `topic` and `known` are null until the job has a result. */
export interface JobStatus {
  status: string;
  topic: { id: number; category: string; label: string } | null;
  known: boolean | null;
}

/** One row of `GET /marks`. */
export interface MarkRow {
  topic_id: number;
  category: string;
  topic: string;
  status: string;
}

export class CoreClient {
  private readonly baseUrl: string;
  private token: string | undefined;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: CoreClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.token = opts.token;
    this.timeoutMs = opts.timeoutMs;
    this.fetchImpl = opts.fetchImpl ?? ((input, init) => fetch(input, init));
  }

  /** Redeem an enrolment code; returns the device token and keeps it for later calls. */
  async enrol(code: string, label: string): Promise<string> {
    const res = await this.request<{ token: string }>("POST", "/auth/enrol", { code, label });
    this.token = res.token;
    return res.token;
  }

  /** Queue a tagging job for `payload`; returns the job id. */
  async enqueue(payload: string): Promise<number> {
    const res = await this.request<{ id: number }>("POST", "/jobs", { payload });
    return res.id;
  }

  /** Status of one of the caller's jobs. */
  jobStatus(id: number): Promise<JobStatus> {
    return this.request<JobStatus>("GET", `/jobs/${id}`);
  }

  /** Mark a topic as known. */
  async setKnown(topicId: number): Promise<void> {
    await this.request("PUT", `/marks/${topicId}`, { status: "known" });
  }

  /** All marks of the caller. */
  listMarks(): Promise<MarkRow[]> {
    return this.request<MarkRow[]>("GET", "/marks");
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let res: Response;
      try {
        res = await this.fetchImpl(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });
      } catch {
        if (controller.signal.aborted) throw new CoreTimeoutError();
        throw new CoreOfflineError();
      }
      if (res.status === 401) throw new CoreAuthError();
      if (!res.ok) throw new CoreHttpError(res.status);
      if (res.status === 204) return undefined as T;
      return (await res.json()) as T;
    } catch (err) {
      if (controller.signal.aborted && !(err instanceof CoreTimeoutError)) throw new CoreTimeoutError();
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }
}
