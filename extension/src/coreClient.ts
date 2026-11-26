/** HTTP client for the local kata core: enrol, jobs, marks. Every call has a timeout. */

import type {
  CourseAccepted,
  CourseListMeta,
  CourseSummary,
  ConceptMark,
  LessonCheckResult,
  MarkRow,
  ProgressDoc,
  ReviewArea,
  ReviewConcept,
  ReviewConceptFilter,
  ReviewFilter,
  ScanClassification,
  ScanExtractInput,
  TopicOverview,
  BlockState,
  ConceptAlias,
  ConceptListRow,
  ConceptSortField,
  ConceptSortOrder,
  IgnoredConcept,
  Joke,
  JokeSource,
  SummaryReply,
} from "./coreClientTypes";
export type {
  MarkRow,
  ConceptMark,
  ScanTopicCandidate,
  ScanClassification,
  ScanConceptCandidate,
  ScanConceptItem,
  ScanBlockOutput,
  ScanExtractInput,
  TopicOverview,
  LessonCheckResult,
  ProgressDoc,
  CourseSummary,
  CourseListMeta,
  CourseAccepted,
  ReviewArea,
  ReviewConcept,
  ReviewConceptFilter,
  ReviewCounts,
  ReviewFilter,
  ReviewOrder,
  ReviewSort,
  ReviewTopic,
  BlockState,
  ConceptAlias,
  ConceptListRow,
  ConceptSortField,
  ConceptSortOrder,
  IgnoredConcept,
  Joke,
  JokeSource,
  SummaryReply,
} from "./coreClientTypes";


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
  /** Stored output of a modelhost job; null until the worker reports it. */
  output?: Record<string, unknown> | null;
}

/** Output of a finished modelhost job (`ok` and `text` are required, `capabilities` optional). */
export interface ModelhostOutput {
  ok: boolean;
  text: string;
  capabilities?: Record<string, unknown>;
}

/** Engine named by a `modelhost.use` job. */
export type ModelhostEngine = "ollama" | "strata" | "none";

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
    case "needs_cloud":
      return "This needs a cloud model. Add a cloud token to turn it on.";
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

  /** Queue a modelhost job of `kind` with a JSON `payload`; returns the job id. Throws CoreHttpError (422) when refused. */
  private async enqueueKind(kind: string, payload: string): Promise<number> {
    const res = await this.request<{ id: number }>("POST", "/jobs", { payload, kind });
    return res.id;
  }

  /** Queue `modelhost.up` (start the local model host); returns the job id. */
  modelhostUp(): Promise<number> {
    return this.enqueueKind("modelhost.up", "{}");
  }

  /** Queue `modelhost.use` (choose the engine); returns the job id. */
  modelhostUse(engine: ModelhostEngine): Promise<number> {
    return this.enqueueKind("modelhost.use", JSON.stringify({ engine }));
  }

  /** Queue `modelhost.measure` (measure the local model); returns the job id. */
  modelhostMeasure(): Promise<number> {
    return this.enqueueKind("modelhost.measure", "{}");
  }

  /** Queue `modelhost.status` (read the local model host state); returns the job id. */
  modelhostStatus(): Promise<number> {
    return this.enqueueKind("modelhost.status", "{}");
  }

  /**
   * One check of a modelhost job: its output when done, "pending" while it has none yet.
   * Throws Error when the job failed. The caller polls.
   */
  async modelhostResult(id: number): Promise<ModelhostOutput | "pending"> {
    const status = await this.jobStatus(id);
    if (status.status === "failed") throw new Error(`modelhost job ${id} failed`);
    if (status.status !== "done" || !status.output) return "pending";
    return status.output as unknown as ModelhostOutput;
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

  /** Area > topic tree of the caller's concepts that match the filter, with state counts (`GET /v1/review/tree`). */
  reviewTree(filter: ReviewFilter = {}): Promise<ReviewArea[]> {
    return this.request<ReviewArea[]>("GET", `/v1/review/tree?${reviewQuery(filter).toString()}`);
  }

  /** The caller's concepts that match the filter, in the given sort and order (`GET /v1/review/concepts`). */
  reviewConcepts(filter: ReviewConceptFilter = {}): Promise<ReviewConcept[]> {
    const query = reviewQuery(filter);
    if (filter.sort !== undefined) query.set("sort", filter.sort);
    if (filter.order !== undefined) query.set("order", filter.order);
    return this.request<ReviewConcept[]>("GET", `/v1/review/concepts?${query.toString()}`);
  }

  /** Check which of the given concepts the caller knows; results come in input order. */
  async lessonCheck(conceptIds: number[]): Promise<LessonCheckResult[]> {
    const res = await this.request<{ results: LessonCheckResult[] }>("POST", "/lesson-check", {
      concept_ids: conceptIds,
    });
    return res.results;
  }

  /** Queue `scan.classify` for a page (`page_key` is its URL without fragment); returns the job id. */
  scanClassify(pageKey: string, text: string, taxonomy: string): Promise<number> {
    return this.enqueueKind("scan.classify", JSON.stringify({ page_key: pageKey, text, taxonomy }));
  }

  /** Queue `scan.extract` for the blocks of one topic; returns the job id. */
  scanExtract(input: ScanExtractInput): Promise<number> {
    const payload = {
      area_id: input.areaId,
      topic_id: input.topicId,
      blocks: input.blocks,
      area: input.area,
      topic: input.topic,
      known: input.known,
    };
    return this.enqueueKind("scan.extract", JSON.stringify(payload));
  }

  /** The stored classification of a page, or null when the core has none (404). */
  async getClassification(pageKey: string): Promise<ScanClassification | null> {
    try {
      const res = await this.request<{
        area_id?: number;
        topic_id: number;
        area: string;
        topic: string;
        candidates: { topic_id: number; area: string; topic: string }[];
      }>("GET", `/scan/classification?page_key=${encodeURIComponent(pageKey)}`);
      return {
        areaId: res.area_id,
        topicId: res.topic_id,
        area: res.area,
        topic: res.topic,
        candidates: res.candidates.map((c) => ({ topicId: c.topic_id, area: c.area, topic: c.topic })),
      };
    } catch (err) {
      if (err instanceof CoreHttpError && err.status === 404) return null;
      throw err;
    }
  }

  /** Remember the concept the caller picked for a written word in a topic. */
  async chooseConcept(topicId: number, word: string, conceptId: number): Promise<void> {
    await this.request("POST", "/scan/choice", { topic_id: topicId, word, concept_id: conceptId });
  }

  /** Move a written word from one concept to another and teach the alias. */
  async reassignConcept(topicId: number, word: string, fromConceptId: number, toConceptId: number): Promise<void> {
    await this.request("POST", "/scan/reassign", {
      topic_id: topicId,
      word,
      from_concept_id: fromConceptId,
      to_concept_id: toConceptId,
    });
  }

  /** Concept counts and concept list of one topic. */
  async topicOverview(topicId: number): Promise<TopicOverview> {
    const res = await this.request<{
      topic_id: number;
      area: string;
      topic: string;
      counts: { new: number; learning: number; known: number };
      concepts: { concept_id: number; label: string; state: ConceptMark["state"] }[];
    }>("GET", `/scan/overview?topic_id=${topicId}`);
    return {
      topicId: res.topic_id,
      area: res.area,
      topic: res.topic,
      counts: res.counts,
      concepts: res.concepts.map((c) => ({ conceptId: c.concept_id, label: c.label, state: c.state })),
    };
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

  /** Visible concepts the caller does not ignore, sorted (`GET /concepts/sorted`). */
  sortedConcepts(sort: ConceptSortField = "name", order: ConceptSortOrder = "asc"): Promise<ConceptListRow[]> {
    return this.request<ConceptListRow[]>("GET", `/concepts/sorted?${new URLSearchParams({ sort, order }).toString()}`);
  }

  /** Derived state of a block of concepts from the caller's marks (`POST /concepts/block-state`). */
  async blockState(conceptIds: number[]): Promise<BlockState> {
    const res = await this.request<{ state: BlockState }>("POST", "/concepts/block-state", { concept_ids: conceptIds });
    return res.state;
  }

  /** Stamp the last-viewed time of a concept (`POST /concepts/{id}/viewed`). */
  async markConceptViewed(conceptId: number): Promise<void> {
    await this.request("POST", `/concepts/${conceptId}/viewed`);
  }

  /** Concepts the caller ignores (`GET /concepts/ignored`). */
  listIgnored(): Promise<IgnoredConcept[]> {
    return this.request<IgnoredConcept[]>("GET", "/concepts/ignored");
  }

  /** Shared and own aliases of a concept (`GET /concepts/{id}/aliases`). */
  listConceptAliases(conceptId: number): Promise<ConceptAlias[]> {
    return this.request<ConceptAlias[]>("GET", `/concepts/${conceptId}/aliases`);
  }

  /** Add a private alias to a concept (`POST /concepts/{id}/aliases`). Throws CoreHttpError 409 when it exists. */
  addConceptAlias(conceptId: number, alias: string): Promise<ConceptAlias> {
    return this.request<ConceptAlias>("POST", `/concepts/${conceptId}/aliases`, { alias });
  }

  /** Summary of a page: the cached one (200) or a queued job id (202) (`POST /summary`). */
  requestSummary(url: string, text: string): Promise<SummaryReply> {
    return this.request<SummaryReply>("POST", "/summary", { url, text });
  }

  /** The cached summary of a page text, or null when none is cached (`GET /summary`, 404). */
  async cachedSummary(url: string, textSha256: string): Promise<string | null> {
    try {
      const res = await this.request<{ summary: string }>(
        "GET",
        `/summary?${new URLSearchParams({ url, text_sha256: textSha256 }).toString()}`,
      );
      return res.summary;
    } catch (err) {
      if (err instanceof CoreHttpError && err.status === 404) return null;
      throw err;
    }
  }

  /** The next cached joke (`GET /jokes/next`). Null when jokes are off or none is cached (404). */
  async nextJoke(): Promise<Joke | null> {
    try {
      return await this.request<Joke>("GET", "/jokes/next");
    } catch (err) {
      if (err instanceof CoreHttpError && err.status === 404) return null;
      throw err;
    }
  }

  /** The enabled joke sources, in list order (`GET /jokes/sources`). */
  listJokeSources(): Promise<JokeSource[]> {
    return this.request<JokeSource[]>("GET", "/jokes/sources");
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

/** Query string of the review filters: `q`, a repeated `state`, and `ids` (an empty set sends `ids=`). */
function reviewQuery(filter: ReviewFilter): URLSearchParams {
  const query = new URLSearchParams();
  if (filter.q !== undefined) query.set("q", filter.q);
  for (const state of filter.states ?? []) query.append("state", state);
  if (filter.ids !== undefined) query.set("ids", filter.ids.join(","));
  return query;
}
