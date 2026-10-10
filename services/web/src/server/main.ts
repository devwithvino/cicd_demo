import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createApp, log } from "./app.js";
import { loadConfig } from "./config.js";
import { flushSentry, initSentry, release } from "./monitoring.js";

const cfg = loadConfig();
if (initSentry(cfg)) log("info", "sentry error reporting enabled", { release: release(cfg) });
const staticDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const server = createServer(createApp(cfg, { staticDir }));

server.listen(cfg.port, () => {
  log("info", "web listening", {
    port: cfg.port,
    environment: cfg.environment,
    version: cfg.version,
    commit: cfg.commit,
  });
});

function shutdown(signal: string): void {
  log("info", "shutdown signal received, draining connections", { signal });
  server.close(() => void flushSentry().finally(() => process.exit(0)));
  setTimeout(() => process.exit(0), 10_000).unref();
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
