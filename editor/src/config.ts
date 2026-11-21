// Editor settings the poster needs. The getter is injected: the host passes a reader over its
// settings, tests pass a plain function. A missing or mistyped value reads as empty.
export interface KataConfig {
  serverUrl: string;
  token: string;
  stopPatterns: string[];
}

export type ConfigGetter = (key: string) => unknown;

export function readConfig(get: ConfigGetter): KataConfig {
  const serverUrl = get("kata.serverUrl");
  const token = get("kata.token");
  const stopPatterns = get("kata.stopPatterns");
  return {
    serverUrl: typeof serverUrl === "string" ? serverUrl : "",
    token: typeof token === "string" ? token : "",
    stopPatterns: Array.isArray(stopPatterns)
      ? stopPatterns.filter((p): p is string => typeof p === "string")
      : [],
  };
}
