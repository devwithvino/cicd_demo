import { describe, expect, it } from "vitest";

import { loadConfig } from "./config.js";
import { initSentry, release } from "./monitoring.js";

describe("monitoring", () => {
  it("stays off without a DSN", () => {
    expect(initSentry(loadConfig({ APP_ENV: "local" }))).toBe(false);
  });

  it("names the release after the baked version", () => {
    expect(release(loadConfig({ APP_VERSION: "1.2.3" }))).toBe("shipyard@1.2.3");
  });

  it("turns on with a DSN", () => {
    expect(initSentry(loadConfig({ APP_ENV: "staging", SENTRY_DSN: "https://public@example.ingest.sentry.io/1" }))).toBe(true);
  });
});
