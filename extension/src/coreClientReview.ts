/** Core client helpers for the review screen: the query string shared by the review reads. */

import type { ReviewFilter } from "./coreClientTypes";

/** Query string of the review filters: `q`, a repeated `state`, and `ids` (an empty set sends `ids=`). */
export function reviewQuery(filter: ReviewFilter): URLSearchParams {
  const query = new URLSearchParams();
  if (filter.q !== undefined) query.set("q", filter.q);
  for (const state of filter.states ?? []) query.append("state", state);
  if (filter.ids !== undefined) query.set("ids", filter.ids.join(","));
  return query;
}
