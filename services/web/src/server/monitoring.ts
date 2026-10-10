// Error reporting to Sentry. Switched on only when SENTRY_DSN is set, which
// the pipeline does for staging and production. Local runs, Kind and previews
// send nothing.
import * as Sentry from "@sentry/node";

import type { Config } from "./config.js";

export function release(cfg: Config): string {
  return `shipyard@${cfg.version}`;
}

export function initSentry(cfg: Config): boolean {
  if (!cfg.sentryDsn) return false;
  Sentry.init({
    dsn: cfg.sentryDsn,
    environment: cfg.environment,
    release: release(cfg),
    tracesSampleRate: 0,
    // Error reporting only: no tracing, and the SDK defaults send no
    // personal data such as IPs or cookies.
    initialScope: { tags: { service: "web", commit: cfg.commit } },
  });
  return true;
}

export function captureError(error: unknown, requestId: string): void {
  Sentry.captureException(error, { tags: { request_id: requestId } });
}

export async function flushSentry(): Promise<void> {
  await Sentry.flush(2000);
}
