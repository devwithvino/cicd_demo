// Browser dashboard. Builds the DOM with textContent only, never innerHTML,
// so data coming back from the API can not inject markup.

import { formatUptime, sameCommit, shortSha, themeFor } from "../shared/format.js";

interface VersionInfo {
  service?: string;
  version?: string;
  commit?: string;
  commitUrl?: string;
  environment?: string;
  uptimeSeconds?: number;
  imageRef?: string;
  startedAt?: string;
}

interface ServiceStatus {
  name: string;
  healthy: boolean;
  state: "up" | "waking" | "down";
  version?: VersionInfo;
  error?: string;
}

interface StatusResponse {
  environment: string;
  queueDepth: number;
  services: ServiceStatus[];
}

interface Job {
  id: string;
  payload: string;
  status: string;
  result?: string;
  submittedBy?: string;
  processedBy?: string;
}

interface PageConfig {
  environment: string;
  repoUrl: string;
  statusPageUrl: string;
  sentryDsn?: string;
  release?: string;
}

interface SentryBrowser {
  init(options: Record<string, unknown>): void;
}

declare global {
  interface Window {
    Sentry?: SentryBrowser;
  }
}

// Pinned Sentry browser bundle, verified by its integrity hash before it runs.
const SENTRY_BUNDLE = "https://browser.sentry-cdn.com/11.6.0/bundle.min.js";
const SENTRY_INTEGRITY = "sha384-rlznaM0ZTdlKZRMeVO8a43/HbvKhLqHABk8FFcshozlZDT84nCfG8GdTIWeQioHe";

/** Report browser errors to Sentry, only when the server provides a DSN. */
function enableSentry(cfg: PageConfig): void {
  if (!cfg.sentryDsn) return;
  const script = document.createElement("script");
  script.src = SENTRY_BUNDLE;
  script.integrity = SENTRY_INTEGRITY;
  script.crossOrigin = "anonymous";
  script.onload = () => {
    window.Sentry?.init({
      dsn: cfg.sentryDsn,
      environment: cfg.environment,
      release: cfg.release,
      initialScope: { tags: { service: "web-browser" } },
    });
  };
  document.head.appendChild(script);
}

const REFRESH_MS = 10_000;
const JOB_POLL_MS = 1_000;
const JOB_TIMEOUT_MS = 120_000;

function byId<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: { className?: string; text?: string; href?: string } = {},
  children: Node[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (props.className) node.className = props.className;
  if (props.text !== undefined) node.textContent = props.text;
  if (props.href && node instanceof HTMLAnchorElement) {
    node.href = props.href;
    node.target = "_blank";
    node.rel = "noopener noreferrer";
  }
  children.forEach((child) => node.appendChild(child));
  return node;
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return (await res.json()) as T;
}

function row(term: string, value: Node | string): Node[] {
  return [el("dt", { text: term }), typeof value === "string" ? el("dd", { text: value }) : el("dd", {}, [value])];
}

function commitNode(info: VersionInfo | undefined): Node | string {
  const sha = shortSha(info?.commit);
  return info?.commitUrl ? el("a", { text: sha, href: info.commitUrl }) : sha;
}

function serviceCard(service: ServiceStatus): HTMLElement {
  const info = service.version;
  const details: Node[] = service.name === "keyvalue"
    ? [...row("role", "job queue"), ...row("plan", "free tier")]
    : [
        ...row("version", info?.version ?? "n/a"),
        ...row("commit", commitNode(info)),
        ...row("env", info?.environment ?? "n/a"),
        ...row("uptime", formatUptime(info?.uptimeSeconds)),
      ];
  if (info?.imageRef) details.push(...row("image", info.imageRef.split("@")[1]?.slice(0, 19) ?? info.imageRef));
  if (service.error && service.state !== "up") details.push(...row("note", service.error));

  return el("article", { className: `card ${service.state}` }, [
    el("div", { className: "card-head" }, [
      el("h3", { text: service.name }),
      el("span", { className: `state ${service.state}`, text: service.state }),
    ]),
    el("dl", {}, details),
  ]);
}

async function refreshServices(): Promise<void> {
  const grid = byId("services");
  const web = await getJson<VersionInfo>("/version").catch(() => undefined);
  const services: ServiceStatus[] = [
    { name: "web", healthy: !!web, state: web ? "up" : "down", version: web },
  ];

  try {
    const status = await getJson<StatusResponse>("/api/status");
    services.push(...status.services);
  } catch {
    services.push({ name: "api", healthy: false, state: "waking", error: "waiting for the API to respond" });
  }

  grid.replaceChildren(...services.map(serviceCard));
  byId("wake-note").hidden = !services.some((s) => s.state === "waking");
  byId("checked-at").textContent = `checked ${new Date().toLocaleTimeString()}`;

  const badge = byId("build-badge");
  const commits = services.filter((s) => s.name !== "keyvalue").map((s) => s.version?.commit);
  if (sameCommit(commits) && commits.length >= 3) {
    badge.className = "pill badge-good";
    badge.textContent = `one build everywhere: ${shortSha(commits[0])}`;
  } else {
    badge.className = "pill badge-warn";
    badge.textContent = "builds differ or still loading";
  }
}

async function refreshJobs(): Promise<void> {
  const body = byId("jobs");
  try {
    const { jobs } = await getJson<{ jobs: Job[] }>("/api/jobs");
    if (jobs.length === 0) return;
    body.replaceChildren(
      ...jobs.map((job) =>
        el("tr", {}, [
          el("td", { text: job.id.slice(0, 8) }),
          el("td", { text: job.status }),
          el("td", { text: job.submittedBy ?? "" }),
          el("td", { text: job.processedBy ?? "" }),
          el("td", { className: "result", text: job.result ?? "" }),
        ]),
      ),
    );
  } catch {
    // The services grid already explains when the API is waking up.
  }
}

function showStep(status: string): void {
  const order = ["queued", "processing", "done"];
  const reached = order.indexOf(status);
  document.querySelectorAll<HTMLLIElement>("#job-steps li").forEach((li, index) => {
    li.classList.remove("active", "complete", "failed");
    if (status === "failed" && index === order.length - 1) li.classList.add("failed");
    else if (index < reached || status === "done") li.classList.add("complete");
    else if (index === reached) li.classList.add("active");
  });
}

async function runJob(event: SubmitEvent): Promise<void> {
  event.preventDefault();
  const input = byId<HTMLInputElement>("job-payload");
  const button = byId<HTMLButtonElement>("job-submit");
  const message = byId("job-message");
  button.disabled = true;
  byId("job-steps").hidden = false;
  showStep("queued");
  message.textContent = "Submitting...";

  try {
    const job = await getJson<Job>("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload: input.value }),
    });
    const deadline = Date.now() + JOB_TIMEOUT_MS;
    let current = job;
    while (current.status !== "done" && current.status !== "failed" && Date.now() < deadline) {
      showStep(current.status);
      message.textContent = current.status === "queued"
        ? "Waiting for the worker. A sleeping free tier worker takes about a minute to wake."
        : `Processing on ${current.processedBy ?? "worker"}...`;
      await new Promise((resolve) => setTimeout(resolve, JOB_POLL_MS));
      current = await getJson<Job>(`/api/jobs/${encodeURIComponent(job.id)}`);
    }
    showStep(current.status);
    message.textContent = current.status === "done"
      ? `Done by ${current.processedBy ?? "worker"}: ${current.result ?? ""}`
      : `Job ended as ${current.status}.`;
    input.value = "";
    void refreshJobs();
  } catch (error) {
    showStep("failed");
    message.textContent = `Job could not be submitted: ${String(error)}`;
  } finally {
    button.disabled = false;
  }
}

function renderLinks(cfg: PageConfig): void {
  const links: [string, string][] = [];
  if (cfg.repoUrl) {
    links.push(
      ["Pipeline runs", `${cfg.repoUrl}/actions`],
      ["Releases with SBOM and provenance", `${cfg.repoUrl}/releases`],
      ["Security scan results", `${cfg.repoUrl}/security`],
      ["Source code", cfg.repoUrl],
    );
  }
  if (cfg.statusPageUrl) links.unshift(["Pipeline status and DORA metrics", cfg.statusPageUrl]);
  const list = byId("release-links");
  list.replaceChildren(
    ...(links.length
      ? links.map(([label, href]) => el("li", {}, [el("a", { text: label, href })]))
      : [el("li", { className: "muted", text: "Links appear once the pipeline deploys this app." })]),
  );
}

async function init(): Promise<void> {
  const cfg = await getJson<PageConfig>("/config.json").catch(
    (): PageConfig => ({ environment: "unknown", repoUrl: "", statusPageUrl: "" }),
  );
  enableSentry(cfg);
  document.body.dataset.theme = themeFor(cfg.environment);
  byId("env-pill").textContent = cfg.environment;
  document.title = `Shipyard (${cfg.environment})`;
  renderLinks(cfg);

  byId<HTMLFormElement>("job-form").addEventListener("submit", (event) => void runJob(event));
  const tick = (): void => {
    void refreshServices();
    void refreshJobs();
  };
  tick();
  setInterval(tick, REFRESH_MS);
}

void init();
