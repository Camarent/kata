/**
 * Core client calls for courses: delete, and the user-facing text of a failed course create or delete.
 * Each function takes the CoreClient and goes through its one request path (auth, timeout, error mapping).
 */

import type { CoreClient } from "./coreClient";
import { CoreHttpError } from "./coreClientErrors";

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

/** Delete a course. Resolves true when deleted, false when it was already gone (404). */
export async function deleteCourse(client: CoreClient, courseId: number): Promise<boolean> {
  try {
    await client.request<void>("DELETE", `/v1/courses/${courseId}`);
    return true;
  } catch (err) {
    if (err instanceof CoreHttpError && err.status === 404) return false;
    throw err;
  }
}
