/**
 * Core client calls for concepts and scanned pages. Each function takes the CoreClient and goes
 * through its one request path (auth, timeout, error mapping).
 */

import type { CoreClient } from "./coreClient";
import { CoreHttpError } from "./coreClientErrors";
import type { ConceptMark, ScanClassification, TopicOverview } from "./coreClientTypes";

/** The stored classification of a page, or null when the core has none (404). */
export async function getClassification(client: CoreClient, pageKey: string): Promise<ScanClassification | null> {
  try {
    const res = await client.request<{
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

/** Concept counts and concept list of one topic. */
export async function topicOverview(client: CoreClient, topicId: number): Promise<TopicOverview> {
  const res = await client.request<{
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
