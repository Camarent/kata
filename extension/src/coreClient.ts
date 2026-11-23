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

/** One concept mark of `GET /concepts/marks`. */
export interface ConceptMark {
  concept_id: number;
  label: string;
  state: "known" | "learning" | "new";
  evidence: string;
  created_at: string;
  updated_at: string;
}

/** One answer of `POST /lesson-check`. `state` is "abstain" when the core has no evidence. */
export interface LessonCheckResult {
  concept_id: number;
  label: string;
  state: "known" | "learning" | "abstain";
  source: string;
  evidence: string;
}

/** A course progress document: item id to {ok, bad} counts (the core checks the shape). */
export type ProgressDoc = Record<string, unknown>;

/** One course of `GET /v1/courses`. */
export interface CourseSummary {
  id: number;
  title: string;
  status: string;
  concept_ids: number[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

/** `GET /v1/courses` with the caller's limit and total course count. */
export interface CourseListMeta {
  items: CourseSummary[];
  limit: number;
  total: number;
}

/** Answer of `POST /v1/courses` (HTTP 202): the new course and the job building it. */
export type CourseAccepted = CourseSummary & { job_id: number };

/** Short, user-facing text for a failed course create or delete. */
export function courseErrorText(err: unknown): string {
  const code = err instanceof CoreHttpError ? err.code : undefined;
  switch (code) {
    case "course_limit":
      return "You have reached your course limit. Delete a course to add another.";
    case "course_name_taken":
      return "A course with this name already exists. Choose another title.";
    case "course_title_empty":
      return "Enter a course title.";
    default:
      return "Could not save the course. Try again.";
  }
}

/** Answer of `GET /v1/courses/{id}/progress`. `revision` is 0 and `doc` null when never saved. */
export interface CourseProgress {
  revision: number;
  doc: ProgressDoc | null;
}

/** Answer of `GET /v1/health/deep`: `status` is "fail" (HTTP 503) when a check failed. */
export interface HealthReport {
  status: "ok" | "fail";
  checks: Record<string, boolean>;
}

/** True when `value` has the shape of the kata health document. */
function isHealthReport(value: unknown): value is HealthReport {
  if (typeof value !== "object" || value === null) return false;
  const { status, checks } = value as { status?: unknown; checks?: unknown };
  if (status !== "ok" && status !== "fail") return false;
  if (typeof checks !== "object" || checks === null) return false;
  return Object.values(checks).every((passed) => typeof passed === "boolean");
}

/** Answer of `PUT /v1/courses/{id}/progress`. */
export interface ProgressSaved {
  revision: number;
  evidence_written: number;
}

/** Options of one request: a pre-serialised body (sent as is) and an `If-Match` revision. */
/** The stable `detail.code` of an error body, or undefined when the body has none. */
async function errorCode(res: Response): Promise<string | undefined> {
  const body = (await res.json().catch(() => undefined)) as { detail?: unknown } | undefined;
  const detail = body?.detail;
  if (typeof detail !== "object" || detail === null) return undefined;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : undefined;
}

interface RequestOptions {
  rawBody?: string;
  ifMatch?: number;
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

  /**
   * Checks that `baseUrl` is a kata core: unauthenticated `GET /v1/health/deep`. Resolves for a
   * kata health document (also a 503 "fail" one). Throws CoreUnreachableError when there is no
   * answer in time, NotKataServerError when the answer is not that document.
   */
  async probe(): Promise<HealthReport> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let res: Response;
      try {
        res = await this.fetchImpl(`${this.baseUrl}/v1/health/deep`, {
          method: "GET",
          signal: controller.signal,
        });
      } catch {
        throw new CoreUnreachableError();
      }
      let body: unknown;
      try {
        body = await res.json();
      } catch {
        if (controller.signal.aborted) throw new CoreUnreachableError();
        throw new NotKataServerError();
      }
      if (!isHealthReport(body)) throw new NotKataServerError();
      return body;
    } finally {
      clearTimeout(timer);
    }
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

  /** All concept marks of the caller. */
  listConceptMarks(): Promise<ConceptMark[]> {
    return this.request<ConceptMark[]>("GET", "/concepts/marks");
  }

  /** Set the state of one concept mark; `evidence` is optional free text. */
  setConceptMark(conceptId: number, state: ConceptMark["state"], evidence = ""): Promise<ConceptMark> {
    return this.request<ConceptMark>("PUT", `/concepts/${conceptId}/mark`, { state, evidence });
  }

  /** Check which of the given concepts the caller knows; results come in input order. */
  async lessonCheck(conceptIds: number[]): Promise<LessonCheckResult[]> {
    const res = await this.request<{ results: LessonCheckResult[] }>("POST", "/lesson-check", {
      concept_ids: conceptIds,
    });
    return res.results;
  }

  /** The caller's ready courses, newest first (first page of `GET /v1/courses`). */
  async listCourses(): Promise<CourseSummary[]> {
    const res = await this.request<{ items: CourseSummary[] }>("GET", "/v1/courses");
    return res.items.filter((course) => course.status === "ready");
  }

  /** As listCourses, plus the course limit and total count (for "n of limit"). */
  async listCoursesMeta(): Promise<CourseListMeta> {
    const res = await this.request<CourseListMeta>("GET", "/v1/courses");
    return { items: res.items.filter((course) => course.status === "ready"), limit: res.limit, total: res.total };
  }

  /** Queue a new course (`POST /v1/courses`). Throws CoreHttpError with `code` on 409/422. */
  createCourse(title: string): Promise<CourseAccepted> {
    return this.request<CourseAccepted>("POST", "/v1/courses", { title });
  }

  /** Delete a course. Resolves true when deleted, false when it was already gone (404). */
  async deleteCourse(courseId: number): Promise<boolean> {
    try {
      await this.request<void>("DELETE", `/v1/courses/${courseId}`);
      return true;
    } catch (err) {
      if (err instanceof CoreHttpError && err.status === 404) return false;
      throw err;
    }
  }

  /** Open a ready course; returns the URL the panel should show it at. */
  async openCourse(courseId: number): Promise<string> {
    const res = await this.request<{ url: string }>("POST", `/v1/courses/${courseId}/open`);
    return res.url;
  }

  /** The stored progress document of a course and its revision. */
  getProgress(courseId: number): Promise<CourseProgress> {
    return this.request<CourseProgress>("GET", `/v1/courses/${courseId}/progress`);
  }

  /**
   * Save a progress document (already serialised as JSON) when `revision` is still the stored one.
   * Throws CoreConflictError (412) when the revision moved.
   */
  putProgress(courseId: number, docJson: string, revision: number): Promise<ProgressSaved> {
    return this.request<ProgressSaved>("PUT", `/v1/courses/${courseId}/progress`, undefined, {
      rawBody: docJson,
      ifMatch: revision,
    });
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    const headers: Record<string, string> = {};
    const payload = options.rawBody ?? (body === undefined ? undefined : JSON.stringify(body));
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    if (options.ifMatch !== undefined) headers["If-Match"] = `"${options.ifMatch}"`;
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let res: Response;
      try {
        res = await this.fetchImpl(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: payload,
          signal: controller.signal,
        });
      } catch {
        if (controller.signal.aborted) throw new CoreTimeoutError();
        throw new CoreOfflineError();
      }
      if (res.status === 401) throw new CoreAuthError();
      if (res.status === 412) {
        const conflict = (await res.json().catch(() => ({}))) as { revision?: number; doc?: ProgressDoc | null };
        throw new CoreConflictError(conflict.revision ?? 0, conflict.doc ?? null);
      }
      if (!res.ok) throw new CoreHttpError(res.status, await errorCode(res));
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
