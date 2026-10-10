import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import type { IncomingMessage, RequestListener, ServerResponse } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";
import { Counter, Histogram, Registry, collectDefaultMetrics } from "@prometheus-io/client";

import { type Config, versionInfo } from "./config.js";

// The API may be cold starting on the free tier, which takes about a minute.
const PROXY_TIMEOUT_MS = 75_000;
const MAX_BODY_BYTES = 8 * 1024;

const CONTENT_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".json": "application/json",
};

const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy":
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Frame-Options": "DENY",
};

export interface AppOptions {
  staticDir: string;
  fetchImpl?: typeof fetch;
  registry?: Registry;
}

export function createApp(cfg: Config, options: AppOptions): RequestListener {
  const fetchImpl = options.fetchImpl ?? fetch;
  const staticRoot = resolve(options.staticDir);
  const registry = options.registry ?? new Registry();
  collectDefaultMetrics({ register: registry, prefix: "shipyard_web_" });

  const requests = new Counter({
    name: "shipyard_http_requests_total",
    help: "HTTP requests handled, by route and status code.",
    labelNames: ["service", "route", "code"],
    registers: [registry],
  });
  const duration = new Histogram({
    name: "shipyard_http_request_duration_seconds",
    help: "HTTP request latency, by route.",
    labelNames: ["service", "route"],
    registers: [registry],
  });

  async function route(req: IncomingMessage, res: ServerResponse): Promise<string> {
    const url = new URL(req.url ?? "/", "http://localhost");
    const path = url.pathname;

    if (path === "/healthz") {
      sendJson(res, 200, { status: "ok" });
      return "/healthz";
    }
    if (path === "/version") {
      sendJson(res, 200, versionInfo(cfg));
      return "/version";
    }
    if (path === "/config.json") {
      sendJson(res, 200, {
        environment: cfg.environment,
        repoUrl: cfg.repoUrl,
        statusPageUrl: cfg.statusPageUrl,
      });
      return "/config.json";
    }
    if (path === "/metrics") {
      res.writeHead(200, { "Content-Type": registry.contentType });
      res.end(await registry.metrics());
      return "/metrics";
    }
    if (path.startsWith("/api/")) {
      await proxy(req, res, path.slice(4) + url.search);
      return "/api";
    }
    if (req.method === "GET" || req.method === "HEAD") {
      await serveStatic(res, path === "/" ? "/index.html" : path);
      return "static";
    }
    sendJson(res, 405, { error: "method not allowed" });
    return "other";
  }

  async function proxy(req: IncomingMessage, res: ServerResponse, target: string): Promise<void> {
    const method = req.method ?? "GET";
    if (method !== "GET" && method !== "POST") {
      sendJson(res, 405, { error: "method not allowed" });
      return;
    }
    const body = method === "POST" ? await readBody(req) : undefined;
    if (body === null) {
      sendJson(res, 413, { error: "request body too large" });
      return;
    }
    try {
      const upstream = await fetchImpl(cfg.apiUrl + target, {
        method,
        body,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": String(res.getHeader("X-Request-ID")),
        },
        signal: AbortSignal.timeout(PROXY_TIMEOUT_MS),
      });
      res.writeHead(upstream.status, {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      });
      res.end(await upstream.text());
    } catch {
      sendJson(res, 502, { error: "api unreachable, it may still be starting up" });
    }
  }

  async function serveStatic(res: ServerResponse, path: string): Promise<void> {
    const file = resolve(join(staticRoot, normalize(path)));
    if (file !== staticRoot && !file.startsWith(staticRoot + sep)) {
      sendJson(res, 404, { error: "not found" });
      return;
    }
    try {
      const content = await readFile(file);
      res.writeHead(200, {
        "Content-Type": CONTENT_TYPES[extname(file)] ?? "application/octet-stream",
        "Cache-Control": extname(file) === ".html" ? "no-cache" : "public, max-age=300",
      });
      res.end(content);
    } catch {
      sendJson(res, 404, { error: "not found" });
    }
  }

  return (req, res) => {
    const started = process.hrtime.bigint();
    const requestId = headerValue(req.headers["x-request-id"]) ?? randomBytes(8).toString("hex");
    res.setHeader("X-Request-ID", requestId);
    for (const [name, value] of Object.entries(SECURITY_HEADERS)) res.setHeader(name, value);

    route(req, res)
      .catch((error: unknown) => {
        log("error", "request failed", { requestId, error: String(error) });
        if (!res.headersSent) sendJson(res, 500, { error: "internal error" });
        return "error";
      })
      .then((name) => {
        const seconds = Number(process.hrtime.bigint() - started) / 1e9;
        requests.inc({ service: "web", route: name, code: String(res.statusCode) });
        duration.observe({ service: "web", route: name }, seconds);
        if (name !== "/healthz" && name !== "static") {
          log("info", "request", {
            requestId,
            method: req.method,
            route: name,
            status: res.statusCode,
            durationMs: Math.round(seconds * 1000),
          });
        }
      });
  };
}

function headerValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

async function readBody(req: IncomingMessage): Promise<string | null> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY_BYTES) return null;
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function sendJson(res: ServerResponse, code: number, body: unknown): void {
  res.writeHead(code, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

export function log(level: string, msg: string, fields: Record<string, unknown> = {}): void {
  process.stdout.write(
    JSON.stringify({ time: new Date().toISOString(), level: level.toUpperCase(), msg, service: "web", ...fields }) + "\n",
  );
}
