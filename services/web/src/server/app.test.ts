import { mkdtempSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Registry } from "@prometheus-io/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApp } from "./app.js";
import { loadConfig } from "./config.js";

let server: Server;
let base: string;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(async () => {
  vi.spyOn(process.stdout, "write").mockImplementation(() => true);
  const staticDir = mkdtempSync(join(tmpdir(), "shipyard-web-"));
  writeFileSync(join(staticDir, "index.html"), "<h1>Shipyard</h1>");

  const cfg = loadConfig({
    APP_ENV: "staging",
    API_URL: "http://api.internal/",
    REPO_URL: "https://example.com/repo",
    APP_VERSION: "1.2.3",
    GIT_SHA: "deadbeefdeadbeef",
  });
  fetchMock = vi.fn();
  const app = createApp(cfg, { staticDir, fetchImpl: fetchMock as unknown as typeof fetch, registry: new Registry() });
  server = createServer(app);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterEach(async () => {
  vi.restoreAllMocks();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

describe("web server", () => {
  it("answers health checks", async () => {
    const res = await fetch(`${base}/healthz`);
    expect(res.status).toBe(200);
    expect(res.headers.get("x-request-id")).toBeTruthy();
  });

  it("reports build metadata and environment", async () => {
    const info = (await (await fetch(`${base}/version`)).json()) as Record<string, unknown>;
    expect(info).toMatchObject({
      service: "web",
      version: "1.2.3",
      environment: "staging",
      commitUrl: "https://example.com/repo/commit/deadbeefdeadbeef",
    });
  });

  it("lets the status page read health and version cross origin", async () => {
    expect((await fetch(`${base}/version`)).headers.get("access-control-allow-origin")).toBe("*");
    expect((await fetch(`${base}/healthz`)).headers.get("access-control-allow-origin")).toBe("*");
    expect((await fetch(`${base}/config.json`)).headers.get("access-control-allow-origin")).toBeNull();
  });

  it("serves runtime config without secrets", async () => {
    const cfg = (await (await fetch(`${base}/config.json`)).json()) as Record<string, unknown>;
    expect(Object.keys(cfg).sort()).toEqual(["environment", "repoUrl", "statusPageUrl"]);
  });

  it("serves the dashboard with security headers", async () => {
    const res = await fetch(`${base}/`);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("Shipyard");
    expect(res.headers.get("content-security-policy")).toContain("default-src 'self'");
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("blocks path traversal", async () => {
    const res = await fetch(`${base}/..%2f..%2fetc%2fpasswd`);
    expect(res.status).toBe(404);
  });

  it("proxies API calls with the request ID", async () => {
    fetchMock.mockResolvedValue(new Response('{"jobs":[]}', { status: 200, headers: { "content-type": "application/json" } }));
    const res = await fetch(`${base}/api/jobs`, { headers: { "x-request-id": "req-1" } });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ jobs: [] });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.internal/jobs");
    expect((init.headers as Record<string, string>)["X-Request-ID"]).toBe("req-1");
  });

  it("forwards POST bodies", async () => {
    fetchMock.mockResolvedValue(new Response('{"id":"j1"}', { status: 202 }));
    const res = await fetch(`${base}/api/jobs`, { method: "POST", body: '{"payload":"x"}' });
    expect(res.status).toBe(202);
    expect((fetchMock.mock.calls[0] as [string, RequestInit])[1].body).toBe('{"payload":"x"}');
  });

  it("rejects oversized bodies", async () => {
    const res = await fetch(`${base}/api/jobs`, { method: "POST", body: "x".repeat(9000) });
    expect(res.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 502 when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("connect ECONNREFUSED"));
    const res = await fetch(`${base}/api/status`);
    expect(res.status).toBe(502);
  });

  it("exposes Prometheus metrics", async () => {
    await fetch(`${base}/healthz`);
    const text = await (await fetch(`${base}/metrics`)).text();
    expect(text).toContain("shipyard_http_requests_total");
  });
});
