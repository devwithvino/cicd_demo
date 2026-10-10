# Shipyard

**Build once. Containerize once. Deploy anywhere. No manual steps. Zero cost.**

[![ci](https://github.com/devwithvino/cicd_demo/actions/workflows/ci.yml/badge.svg)](https://github.com/devwithvino/cicd_demo/actions/workflows/ci.yml)
[![deliver](https://github.com/devwithvino/cicd_demo/actions/workflows/deliver.yml/badge.svg)](https://github.com/devwithvino/cicd_demo/actions/workflows/deliver.yml)
[![release](https://img.shields.io/github/v/release/devwithvino/cicd_demo?label=release)](https://github.com/devwithvino/cicd_demo/releases)
[![images](https://img.shields.io/badge/images-amd64%20%7C%20arm64-blue)](https://github.com/devwithvino?tab=packages&repo_name=cicd_demo)
[![cost](https://img.shields.io/badge/monthly%20cost-%240-brightgreen)](docs/free-tier-limits.md)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

Shipyard is a reference delivery pipeline. A small microservices app travels from a `git push` to a live, verified production deployment, fully automated with GitHub Actions and hosted on free tiers. The app is deliberately simple. **The pipeline is the product.**

## Live demo

| What | Link |
|---|---|
| Production app | https://shipyard-web-production.onrender.com |
| Staging app | https://shipyard-web-staging.onrender.com |
| Releases (versioned images and digests) | https://github.com/devwithvino/cicd_demo/releases |
| Pipeline runs | https://github.com/devwithvino/cicd_demo/actions |

> The demo runs on free instances that sleep after 15 minutes without traffic. The first visit can take about a minute while the services wake up. The dashboard says so and refreshes on its own.

## In 60 seconds

For a business reader, this is what the project shows:

- **Every change is checked automatically.** Code is linted, type checked and tested in three languages before it can ship.
- **Software is built exactly once.** The same container image that passed testing is the one that runs in production. Nothing is rebuilt along the way, so what was tested is what customers get.
- **Releases are verified, not hoped for.** After every deploy, an automated smoke test sends a real job through the live system and confirms every service runs the expected version.
- **People stay in control.** Staging updates automatically. Production needs one click of approval from a named reviewer.
- **Bad releases undo themselves.** If a release fails its checks after going live, the pipeline puts the previous version back on its own, confirms it works, and opens an incident report. In the recorded demo, service was restored in 28 seconds.
- **The team is told what happened.** Every delivery posts a plain language summary to the team chat, with the time it took.
- **It costs nothing to run.** Everything uses free tiers, and the hosting account has no payment method, so a bill is impossible.

### Measured on a real run

Numbers from [delivery run 38020394941](https://github.com/devwithvino/cicd_demo/actions/runs/38020394941), release [v0.1.0](https://github.com/devwithvino/cicd_demo/releases/tag/v0.1.0):

| Stage | Time |
|---|---|
| Build all three services for two CPU architectures, once | 1m 38s |
| Deploy to staging and smoke test | 45s |
| Human approval (not counted as pipeline time) | 1m 39s |
| Deploy the identical images to production and smoke test | 46s |
| Tag the release and publish it | 8s |
| **Commit to production, excluding the approval wait** | **about 3m 40s** |

And from the [deliberate failure demo](https://github.com/devwithvino/cicd_demo/actions/runs/38022224039), which shipped a broken release to staging on purpose:

| Event | Time (UTC) |
|---|---|
| Broken release starts deploying | 03:57:01 |
| Broken release live, health checks still green | 03:57:25 |
| Smoke test catches the defect | 03:57:27 |
| Previous release live again | 03:57:51 |
| Restored release verified | 03:57:55 |
| **Failure detected to service verified** | **28 seconds** |

The pipeline wrote all of this up automatically in [incident #1](https://github.com/devwithvino/cicd_demo/issues/1).

---

## The application

Shipyard is a small job processing system. A visitor types some text on the dashboard, the API queues it, a worker processes it, and the dashboard shows which version of each service handled the work.

| Service | Language | Role | Image |
|---|---|---|---|
| `web` | TypeScript on Node.js 24 | Dashboard and API proxy | `ghcr.io/devwithvino/shipyard-web` |
| `api` | Go 1.26 | Accepts jobs, reports status, aggregates health | `ghcr.io/devwithvino/shipyard-api` (22 MB, distroless) |
| `worker` | Python 3.13 | Processes jobs from the queue | `ghcr.io/devwithvino/shipyard-worker` |
| Key Value | Valkey (Redis compatible) | Job queue and job records | Render managed |

Three languages are used on purpose. They prove the pipeline handles any stack with the same build, scan and deploy steps.

### Architecture

```mermaid
flowchart LR
    user([Visitor's browser])

    subgraph render[Render free tier]
        direction LR
        web[web<br/>TypeScript dashboard]
        api[api<br/>Go service]
        worker[worker<br/>Python consumer]
        kv[(Key Value<br/>job queue)]
    end

    subgraph github[GitHub]
        actions[GitHub Actions<br/>CI/CD pipeline]
        ghcr[(GitHub Container<br/>Registry)]
    end

    user -- HTTPS --> web
    web -- "/api/* proxy" --> api
    api -- "queue job" --> kv
    worker -- "pop job, write result" --> kv
    api -. "health and version check" .-> worker

    actions -- "push images by digest" --> ghcr
    actions -- "deploy digest via Render API" --> render
    render -- "pull image" --> ghcr
```

Each environment (staging and production) runs its own copy of `web`, `api` and `worker`. Both environments share one free Key Value instance, and every key carries an environment prefix (`stg:` or `prd:`), so their data never mixes.

### How a job flows

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as web
    participant A as api
    participant K as Key Value
    participant R as worker

    B->>W: POST /api/jobs {"payload": "ship it"}
    W->>A: POST /jobs (proxied, request ID kept)
    A->>K: save job, push ID onto queue
    A-->>B: 202 Accepted, job queued
    R->>K: pop next job ID (blocking)
    R->>K: status processing, then done with result
    loop every second
        B->>W: GET /api/jobs/{id}
        W->>A: GET /jobs/{id}
        A->>K: read job
        A-->>B: status, result, processed by worker 0.1.0
    end
```

### What the dashboard shows

- A card per service with its **version, commit (linked to GitHub), environment, health and uptime**, plus the exact image digest when deployed by the pipeline.
- A **"one build everywhere"** badge that turns green only when every service reports the same commit.
- A colored banner per environment: green for production, amber for staging, purple for previews, grey for local.
- A **Run a job** panel with live progress (queued, picked up, done) and a table of recent jobs showing which version submitted and processed each one.
- Release links to pipeline runs, releases and security results.

### API endpoints

| Service | Endpoint | Purpose |
|---|---|---|
| all | `GET /healthz` | Liveness. Used by Render's health check |
| all | `GET /version` | Version, commit, build time, environment, uptime, image digest |
| all | `GET /metrics` | Prometheus metrics |
| api, worker | `GET /readyz` | Readiness. Fails when Key Value is unreachable |
| api | `POST /jobs` | Queue a job, body `{"payload": "text"}` |
| api | `GET /jobs`, `GET /jobs/{id}` | Recent jobs, or one job |
| api | `GET /status` | Health of api, Key Value and worker in one call |
| web | `/api/*` | Proxy to the API, so the browser only talks to one origin |

### Built for production habits

- Structured JSON logs with request IDs passed from web to api.
- Graceful shutdown on `SIGTERM`, so deploys drain in-flight requests.
- Separate liveness and readiness probes.
- Containers run as non-root users. The Go image is distroless, with no shell or package manager.
- Strict security headers on the dashboard (Content Security Policy, no framing, no sniffing). The browser code builds the page without `innerHTML`, so API data can't inject markup.
- Runtime settings come from environment variables. Version, commit and build time are baked into the image at build time. That combination is what makes one image deployable anywhere.

---

## The CI/CD pipeline

### Delivery flow

```mermaid
flowchart TD
    push([Merge to main]) --> version[Calculate semantic version<br/>from conventional commits]
    version --> build

    subgraph build[Build once]
        direction LR
        b1[api amd64] & b2[api arm64] & b3[worker amd64] & b4[worker arm64] & b5[web amd64] & b6[web arm64]
    end

    build --> publish[Merge into multi-arch images<br/>push to GHCR, record digests]
    publish --> stg[Deploy digests to staging]
    stg --> stgsmoke{Staging<br/>smoke test}
    stgsmoke -- pass --> stgtag[Move staging tag]
    stgsmoke -- fail --> rb1[Automatic rollback<br/>verify, open incident]
    rb1 --> stop1([Stop. Nothing reaches production])
    stgtag --> approval{{Human approval<br/>production environment}}
    approval -- approved --> prd[Deploy the same digests to production]
    approval -- rejected --> stop2([Stop. Production unchanged])
    prd --> prdsmoke{Production<br/>smoke test}
    prdsmoke -- pass --> prdtag[Move production tag]
    prdtag --> release[Tag images vX.Y.Z and latest<br/>publish GitHub Release]
    release --> report[Measure pipeline time]
    prdsmoke -- fail --> rb2[Automatic rollback<br/>verify, open incident]
    rb2 --> report
    stop1 --> report
    report --> notify[Discord summary]
```

Pull requests run the CI checks below. Merges to `main` run the full delivery flow.

### Build once, promote by digest

A container image is identified by a **digest**, a fingerprint of its exact contents. Shipyard builds each service once per change and then refers to it only by digest. Staging and production receive the identical digest, so the production artifact is byte for byte the one that passed staging.

- **Native multi-arch builds.** Each service is built on a native amd64 runner and a native arm64 runner in parallel, with no slow CPU emulation. The two results are merged into one multi-arch image. Render pulls the amd64 variant, and the same image runs on Apple Silicon laptops and arm64 Kubernetes nodes.
- **Layer caching.** Each service and architecture has its own GitHub Actions cache scope, so unchanged layers are reused.
- **Multi-stage Dockerfiles.** Compilers and dev dependencies stay in the build stage. Runtime images contain only what the service needs.
- **Semantic versions.** [`scripts/next_version.py`](scripts/next_version.py) reads conventional commit messages since the last release tag: `feat` bumps the minor version, `fix` bumps patch, a `!` bumps major.

Tags tell the story of each digest. None of them trigger a rebuild:

| Tag | Meaning | Moves? |
|---|---|---|
| `sha-82bd16f` | Built from this commit | Never |
| `0.1.0-rc.5` | Release candidate from delivery run 5 | Never |
| `main` | Latest build from the main branch | On every build |
| `staging` | Currently verified in staging | Only after a staging smoke test passes |
| `production` | Currently verified in production | Only after a production smoke test passes |
| `0.1.0`, `latest` | Released to production | Added at release |

### Deploying to Render

Render never builds anything. Every service is image backed, and the pipeline tells Render exactly which digest to run through the Render API. [`scripts/render_deploy.py`](scripts/render_deploy.py):

1. Records the image each service runs now. This record is what rollback will use.
2. Sets an `IMAGE_REF` variable so the app can display its own digest.
3. Deploys the new digest to all three services in parallel.
4. Polls each deploy until it is live, fails or times out.

Render then health checks each new instance and only switches traffic once it is healthy. That gives zero downtime deploys even on the free tier.

### Smoke tests

[`scripts/smoke_test.py`](scripts/smoke_test.py) runs after every deploy and writes its report into the run summary:

1. **Warm up.** Waits up to four minutes for every service to answer `/healthz`, because free instances may be asleep.
2. **Version.** Every service must report the commit being deployed. This proves the intended build is the one actually serving traffic.
3. **Wiring.** The web service must reach the API, and the API must reach the worker.
4. **End to end.** A real job is submitted through the public web URL and must be completed by the worker.

The test deliberately goes beyond health checks. A release can be "healthy" and still broken, and the rollback demo relies on exactly that.

### Automatic rollback

Every deploy records which image each service was running before it started. If the deploy or its smoke test fails, [`_deploy-render.yml`](.github/workflows/_deploy-render.yml) immediately:

1. Redeploys the recorded previous images to all services in parallel.
2. Runs the full smoke test again against the restored release.
3. Measures the time from detecting the failure to a verified restore.
4. Opens an [incident issue](https://github.com/devwithvino/cicd_demo/issues?q=label%3Aincident) with a summary, the failed checks and a timeline.
5. Marks the deployment as failed, keeps the environment tag on the last good release, and stops the release from going any further.

There are two layers of protection, and each covers a different kind of failure:

| Layer | Catches | Example |
|---|---|---|
| Render health check | A release that will not start or answer | Crash on boot. Render never switches traffic, the old instance keeps serving |
| Pipeline smoke test and rollback | A release that runs but does the wrong thing | Job submission broken while health checks stay green |

### The deliberate failure demo

[`demo-failure.yml`](.github/workflows/demo-failure.yml) shows the second layer working, on demand. It builds today's code with a deliberate defect (`BROKEN_RELEASE=true`) that breaks job submission but keeps every health check green, so Render is happy to run it. Then it deploys that release to staging, or to production after approval. The smoke test fails at "job accepted", the pipeline rolls back, verifies, opens an incident and posts a red then green summary to Discord.

To run it: **Actions, demo-failure, Run workflow**, choose an environment. The run itself ends red, because the broken release really did fail. The "Verify automatic recovery" job is the one that must be green.

### Manual deploy and one click rollback

Releases stay deployable after they ship. [`deploy-manual.yml`](.github/workflows/deploy-manual.yml) and [`rollback.yml`](.github/workflows/rollback.yml) resolve a version through [`_resolve-release.yml`](.github/workflows/_resolve-release.yml) to the exact digests released for it, then use the same deploy, smoke test and automatic rollback as the main pipeline.

- `rollback` defaults to **previous**: the newest release older than what the environment runs now. It asks for a reason, which goes into the team notification.
- `deploy-manual` takes any released version and has a **dry run** option that only prints the plan.
- Production still requires approval for both.
- An unknown version is refused, with the list of available releases.

### Protecting production from infrastructure syncs

Render redeploys a service whenever its Blueprint (`render.yaml`) changes. If the Blueprint pointed at `main`, an infrastructure edit could push an unapproved build into production. Instead, each environment has its own moving tag that only advances after that environment's smoke test passes. A Blueprint sync can therefore only redeploy an image that already passed in that environment.

### Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | Pull requests, pushes to `main` | Detects which services changed and checks only those. Go: golangci-lint and tests with the race detector. Python: ruff, mypy in strict mode, pytest with coverage. TypeScript: eslint, tsc, vitest with coverage, production build. Plus prose lint. One aggregate "CI passed" check for branch protection |
| [`deliver.yml`](.github/workflows/deliver.yml) | Pushes to `main` (code changes), manual run | The delivery flow above |
| [`_build.yml`](.github/workflows/_build.yml) | Called by other workflows | Reusable build once: native multi-arch matrix, push by digest, merge, tag, output a digest map |
| [`_deploy-render.yml`](.github/workflows/_deploy-render.yml) | Called by other workflows | Reusable deploy to one environment: deploy by digest, smoke test, automatic rollback with incident issue on failure, move the environment tag on success, keep the deploy record for 90 days |
| [`demo-failure.yml`](.github/workflows/demo-failure.yml) | Manual run | Ships a deliberately broken release and verifies the automatic recovery |
| [`rollback.yml`](.github/workflows/rollback.yml) | Manual run | One click rollback to the previous release, or a chosen one |
| [`deploy-manual.yml`](.github/workflows/deploy-manual.yml) | Manual run | Deploy any released version to any environment, with a dry run option |
| [`_notify.yml`](.github/workflows/_notify.yml) | Called by other workflows | Reusable Discord notification with status color, version, commit, timings and links |
| [`_resolve-release.yml`](.github/workflows/_resolve-release.yml) | Called by other workflows | Turns a version, or "previous", into the released digests and commit |

Pipeline practices applied throughout:

- **Least privilege.** Every workflow starts with `permissions: {}` and each job asks only for what it needs.
- **Pinned actions.** Third party actions are pinned to full commit SHAs, not movable tags.
- **Concurrency control.** CI cancels outdated runs on the same pull request. Deliveries run one at a time. Each environment has its own deploy lock shared by every workflow, so a demo, a rollback and a delivery can never deploy to the same environment at once. Deploys are never cancelled midway.
- **Readable summaries.** Every stage writes a Markdown summary to the run page, so anyone can see what was built, where it went and what was checked.

### Environments and secrets

| GitHub environment | Protection | Holds |
|---|---|---|
| `staging` | Automatic | Render API key (secret), service IDs and URLs (variables) |
| `production` | Required reviewer, `main` branch only | Its own Render API key, released to a job only after approval |
| `preview` | Automatic | Reserved for pull request previews |
| `infra` | Required reviewer, `main` branch only | Reserved for infrastructure as code |

- Images are pushed with the short lived `GITHUB_TOKEN`. There is no personal access token anywhere.
- Images are public, so Render needs no registry credential.
- Render does not support OIDC federation, so its API key is stored as an environment secret, scoped per environment.
- The Discord webhook is a repository secret. Notifications skip quietly when it is absent, so forks never fail.

---

## Zero cost, by design

| Piece | Free because |
|---|---|
| GitHub Actions, including arm64 runners | Free and unlimited for public repositories |
| GitHub Container Registry | Free for public images |
| Render web services and Key Value | Free instance types |
| Render build minutes | Not used. Images are built in GitHub Actions |
| Discord notifications | Free webhooks |

Free tiers come with limits: instances sleep after 15 minutes idle, 750 instance hours a month are shared by all services, one free Key Value instance, 5 GB of bandwidth a month, and no free background worker type (so the worker runs as a free web service). Each limit and how the design handles it is documented in [docs/free-tier-limits.md](docs/free-tier-limits.md), together with the results of the platform spike that proved the approach before any code was written.

---

## Run it locally

Requirements: Docker with Compose.

```bash
docker compose up --build
```

Open http://localhost:8080. The stack includes `web`, `api`, `worker` and a Valkey container that mirrors Render Key Value. To bake real build metadata into the local images:

```bash
GIT_SHA=$(git rev-parse HEAD) VERSION=0.1.0-local docker compose up --build
```

To run the released images from GHCR instead of building:

```bash
SHIPYARD_TAG=0.1.0 docker compose up
```

Smoke test the local stack with the same script the pipeline uses:

```bash
python scripts/smoke_test.py --web http://localhost:8080 --api http://localhost:8090 --worker http://localhost:8091
```

### Run the tests

| Service | Command (from the service folder) |
|---|---|
| api | `go test -race ./...` |
| worker | `uv sync && uv run pytest` |
| web | `npm ci && npm test` |
| scripts | `python scripts/prose_lint.py .` |

---

## Repository layout

```text
.
├── services/
│   ├── api/          Go API: cmd/, internal/, tests, Dockerfile
│   ├── worker/       Python worker: src/, tests/, uv.lock, Dockerfile
│   └── web/          TypeScript dashboard: src/server, src/client, public/, Dockerfile
├── scripts/
│   ├── next_version.py    Semantic version from conventional commits
│   ├── render_deploy.py   Deploy, record and roll back image digests on Render
│   ├── smoke_test.py      Post deploy verification used everywhere
│   └── prose_lint.py      House writing style check
├── .github/workflows/     ci, deliver, demo-failure, rollback, deploy-manual and the reusable _ workflows
├── docs/
│   └── free-tier-limits.md
├── render.yaml            Render Blueprint: 6 free web services and 1 Key Value
└── docker-compose.yml     Local stack using the same images
```

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Platform spike: deploy by digest, previews, free tier limits | Done |
| 1 | Application services, tests, Dockerfiles, local stack | Done |
| 2 | CI, build once, staging, approval, production, release, Discord | Done |
| 3 | Automatic rollback, deliberate failure demo, manual deploy and rollback workflows, incident issues | Done |
| 4 | Status page with live health and DORA metrics on GitHub Pages | Next |
| 5 | Security gates: secret scanning, CodeQL, dependency review, image scanning, SBOM, signing and provenance | Planned |
| 6 | Pull request preview environments on Render | Planned |
| 7 | Same images on Kubernetes (Kind in Actions, Helm), performance smoke test, local Grafana | Planned |
| 8 | Terraform for GitHub settings, Dependabot, nightly checks, OpenSSF Scorecard | Planned |
| 9 | Case study, runbook, demo script and services overview | Planned |

## License

MIT, see [LICENSE](LICENSE).
