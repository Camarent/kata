/**
 * Core client calls for tracks, quiz sources and exam results. Each function takes the
 * CoreClient and goes through its one request path (auth, timeout, error mapping).
 */

import type { CoreClient } from "./coreClient";
import type {
  DecisionPoint,
  EnqueueResponse,
  ExamResult,
  MiniQuestion,
  PointIn,
  Track,
  TrackIn,
  TrackPage,
  TrackPatch,
} from "./coreClientTypes";

/** `GET /v1/tracks`: one page, newest first. `beforeId` asks for the page before that track id. */
export function listTracks(client: CoreClient, opts: { limit?: number; beforeId?: number } = {}): Promise<TrackPage> {
  const query = new URLSearchParams();
  if (opts.limit !== undefined) query.set("limit", String(opts.limit));
  if (opts.beforeId !== undefined) query.set("before_id", String(opts.beforeId));
  const qs = query.toString();
  return client.request<TrackPage>("GET", qs ? `/v1/tracks?${qs}` : "/v1/tracks");
}

/** `POST /v1/tracks`: create a track. */
export function createTrack(client: CoreClient, input: TrackIn): Promise<Track> {
  return client.request<Track>("POST", "/v1/tracks", input);
}

/** `GET /v1/tracks/{id}`: one track. */
export function getTrack(client: CoreClient, trackId: number): Promise<Track> {
  return client.request<Track>("GET", `/v1/tracks/${trackId}`);
}

/** `PATCH /v1/tracks/{id}`: change the sent fields of a track. */
export function patchTrack(client: CoreClient, trackId: number, patch: TrackPatch): Promise<Track> {
  return client.request<Track>("PATCH", `/v1/tracks/${trackId}`, patch);
}

/** `DELETE /v1/tracks/{id}`: remove a track. */
export async function deleteTrack(client: CoreClient, trackId: number): Promise<void> {
  await client.request("DELETE", `/v1/tracks/${trackId}`);
}

/** `POST /v1/tracks/{id}/decision-points`: add a decision point after a plan position. */
export function addDecisionPoint(client: CoreClient, trackId: number, input: PointIn): Promise<DecisionPoint> {
  return client.request<DecisionPoint>("POST", `/v1/tracks/${trackId}/decision-points`, input);
}

/** `POST /quiz/sources`: queue a quiz source from a URL (202); returns the job id. */
export async function addQuizSource(client: CoreClient, url: string): Promise<number> {
  const res = await client.request<EnqueueResponse>("POST", "/quiz/sources", { url });
  return res.id;
}

/** `GET /quiz/mini`: up to five cached quiz questions, without the answer index. */
export function miniQuiz(client: CoreClient): Promise<MiniQuestion[]> {
  return client.request<MiniQuestion[]>("GET", "/quiz/mini");
}

/** `POST /exams/import`: store an exam result JSON as pending; changes no mark. */
export function importExamResult(client: CoreClient, payload: string): Promise<ExamResult> {
  return client.request<ExamResult>("POST", "/exams/import", undefined, { rawBody: payload });
}

/** `POST /exams/{id}/confirm`: confirm the listed concepts of an exam result. */
export function confirmExamResult(client: CoreClient, resultId: number, conceptIds: number[]): Promise<ExamResult> {
  return client.request<ExamResult>("POST", `/exams/${resultId}/confirm`, { concept_ids: conceptIds });
}

/** `POST /exams/{id}/dismiss`: dismiss an exam result. */
export function dismissExamResult(client: CoreClient, resultId: number): Promise<ExamResult> {
  return client.request<ExamResult>("POST", `/exams/${resultId}/dismiss`);
}
