/** Types of the kata core answers: marks, concept scan, course list. Type-only, no runtime code. */

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

/** A topic the core offers for a page (`candidates` of a classification). */
export interface ScanTopicCandidate {
  topicId: number;
  area: string;
  topic: string;
}

/** Classification of a page: the topic it belongs to, or `candidates` to choose from. */
export interface ScanClassification {
  /** Area of the topic; the extract job needs it. Absent in replies from an older core (then undefined). */
  areaId?: number;
  topicId: number;
  area: string;
  topic: string;
  candidates: ScanTopicCandidate[];
}

/** Candidate concept a written word may mean (`candidates` of a scan concept item). */
export interface ScanConceptCandidate {
  conceptId: number;
  label: string;
}

/** One word the concept scan found in a block; `conceptId` is null when no concept matched. */
export interface ScanConceptItem {
  word: string;
  conceptId: number | null;
  label: string;
  definition: string;
  state: ConceptMark["state"];
  candidates: ScanConceptCandidate[];
}

/** Output of a `scan.extract` job for one block; `skipped` is set when the block had nothing to teach. */
export interface ScanBlockOutput {
  blockId: string;
  skipped?: boolean;
  concepts: ScanConceptItem[];
}

/** Input of `scanExtract`: the topic and the blocks to extract concepts from. */
export interface ScanExtractInput {
  areaId: number;
  topicId: number;
  blocks: { blockId: string; text: string }[];
  area: string;
  topic: string;
  known: string[];
}

/** Concept counts and concept list of one topic (`GET /scan/overview`). */
export interface TopicOverview {
  topicId: number;
  area: string;
  topic: string;
  counts: { new: number; learning: number; known: number };
  concepts: { conceptId: number; label: string; state: ConceptMark["state"] }[];
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

/** Review filters shared by `GET /v1/review/tree` and `GET /v1/review/concepts`. `ids` is the "Only this page" set. */
export interface ReviewFilter {
  q?: string;
  states?: ConceptMark["state"][];
  ids?: number[];
}

/** Sort of the review concept list (`GET /v1/review/concepts`). */
export type ReviewSort = "name" | "added" | "viewed" | "relevance";

/** Sort order of the review concept list. */
export type ReviewOrder = "asc" | "desc";

/** New, learning and known counts of a review tree node. */
export interface ReviewCounts {
  new: number;
  learning: number;
  known: number;
}

/** One topic of `GET /v1/review/tree`. */
export interface ReviewTopic {
  topicId: number;
  topic: string;
  counts: ReviewCounts;
}

/** One area of `GET /v1/review/tree`. */
export interface ReviewArea {
  area: string;
  counts: ReviewCounts;
  topics: ReviewTopic[];
}

/** Input of `reviewConcepts`: the shared filters plus the list sort. */
export interface ReviewConceptFilter extends ReviewFilter {
  sort?: ReviewSort;
  order?: ReviewOrder;
}

/** One concept of `GET /v1/review/concepts`. Dates are ISO strings; `last_viewed_at` is null when never viewed. */
export interface ReviewConcept {
  concept_id: number;
  label: string;
  state: string;
  added_at: string;
  last_viewed_at: string | null;
  relevance: number;
}

/** Sort fields of `GET /concepts/sorted`. */
export type ConceptSortField = "name" | "added" | "viewed" | "relevance";

/** Sort order of `GET /concepts/sorted`. */
export type ConceptSortOrder = "asc" | "desc";

/** One concept of `GET /concepts/sorted`: the caller's visible concepts that are not ignored. */
export interface ConceptListRow {
  concept_id: number;
  label: string;
  state: string;
  added_at: string;
  last_viewed_at: string | null;
  relevance: number;
}

/** Derived state of a block of concepts (`POST /concepts/block-state`). */
export type BlockState = "new" | "learning" | "known" | "mixed";

/** One ignored concept of `GET /concepts/ignored`. */
export interface IgnoredConcept {
  concept_id: number;
  label: string;
}

/** One alias of a concept (`GET`/`POST /concepts/{id}/aliases`); `private` when the caller owns it. */
export interface ConceptAlias {
  id: number;
  concept_id: number;
  alias: string;
  private: boolean;
}

/** Answer of `POST /summary`: a cached summary (200), or a queued job id (202). */
export type SummaryReply = { status: "done"; summary: string } | { id: number };

/** One joke of `GET /jokes/next`, with its source attribution and licence. */
export interface Joke {
  text: string;
  source_id: string;
  attribution: string;
  licence_name: string;
  licence_url: string;
}

/** One enabled joke source of `GET /jokes/sources`. */
export interface JokeSource {
  id: string;
  attribution: string;
  licence_name: string;
  licence_url: string;
}
