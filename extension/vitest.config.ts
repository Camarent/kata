import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts"],
    // Test files run the shared build (it rm's dist/<browser> first); run them one at a time so builds do not race.
    fileParallelism: false,
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "json-summary"],
      include: ["src/**"],
    },
  },
});
