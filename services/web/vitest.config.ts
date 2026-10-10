import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/server/**/*.ts", "src/shared/**/*.ts"],
      exclude: ["src/**/*.test.ts", "src/server/main.ts"],
      reporter: ["text", "lcov"],
    },
  },
});
