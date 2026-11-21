import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// The editor host API is not installed here: tests map the "vscode" module to a local stub.
export default defineConfig({
  resolve: {
    alias: {
      vscode: fileURLToPath(new URL("./tests/mocks/vscode.ts", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "json-summary"],
      include: ["src/**"],
    },
  },
});
