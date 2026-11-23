/** Result of validating a user-typed server URL. */
export type ServerUrlResult =
  | { ok: true; baseUrl: string; origin: string; pattern: string }
  | { ok: false; reason: string };

/**
 * Checks a server URL typed by the user. Accepts http and https only, with no credentials,
 * query or fragment. Trims trailing slashes and keeps an optional base path. Returns the
 * normalised base URL, its origin and the host pattern `<origin>/*`.
 */
export function validateServerUrl(input: string): ServerUrlResult {
  const trimmed = input.trim();
  if (trimmed === "") {
    return { ok: false, reason: "server URL is empty" };
  }
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return { ok: false, reason: "server URL is not a valid URL" };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { ok: false, reason: "server URL must use http or https" };
  }
  if (url.username !== "" || url.password !== "") {
    return { ok: false, reason: "server URL must not contain credentials" };
  }
  if (url.search !== "" || url.hash !== "") {
    return { ok: false, reason: "server URL must not contain a query or fragment" };
  }
  const origin = url.origin;
  const basePath = url.pathname.replace(/\/+$/, "");
  return { ok: true, baseUrl: `${origin}${basePath}`, origin, pattern: `${origin}/*` };
}
