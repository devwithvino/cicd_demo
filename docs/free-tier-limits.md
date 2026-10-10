# Free Tier Limits and Platform Findings

Shipyard runs at zero cost. This page records every free tier limit that shapes the design, and the results of the Phase 0 platform spike that proved the deployment approach before any real code was written.

Last reviewed: 2026-10-10.

## Render free tier

| Limit | Effect on Shipyard | How the design handles it |
|---|---|---|
| Free web services spin down after 15 minutes without traffic. A cold start takes about one minute. | The first request after idle is slow. Smoke tests could time out. | Smoke tests warm services up with retries for up to three minutes. The demo script pre-warms every service. The dashboard shows cold or warm state openly. |
| 750 free instance hours per workspace per month, shared by every service. | Six services awake all month would need about 4,300 hours. | No keep-alive pings. Spin-down keeps real usage low. The only scheduled traffic is one daily synthetic check. |
| Background workers, cron jobs and private services have no free plan. | A native worker service would cost money. | The worker runs as a free web service: a queue consumer plus a small HTTP server for health, version and metrics. Scheduled jobs run in GitHub Actions. |
| Free web services cannot receive private network traffic. | Services cannot call each other on the internal network. | Services call each other over public HTTPS URLs. Calls to the worker health endpoint also wake it up. |
| One free Key Value instance per workspace, in memory only. | Staging, production and previews share one instance. Data is lost on restart. | Every environment uses its own key prefix. Queue data is disposable by design. |
| Free Postgres is deleted 30 days after creation. | Not suitable for a long lived demo. | Not used. |
| Hobby workspaces include 5 GB of outbound bandwidth per month. Without a payment method, services are suspended until the next month instead of billed. | A traffic spike could pause the demo, but can never create a bill. | Small payloads and no heavy assets. The status page is hosted on GitHub Pages. No payment method is kept on file, which guarantees zero cost. |
| 500 build pipeline minutes per month. | Building on Render would use them up. | All images are built in GitHub Actions. Render only pulls finished images, so Render build minutes stay at zero. |
| Images must be linux/amd64 and at most 10 GB compressed. | Multi-arch images must resolve to amd64. | Verified in the spike (see below). |
| Multi-service Preview Environments require the Pro plan. | The built-in preview feature is not available. | The pipeline uses the service preview API, which works on the free plan, and wires the previews together itself. |
| Image previews are not deleted automatically. | Old previews would pile up. | The pipeline deletes previews when a pull request closes, and a nightly janitor removes any orphans. |
| Built-in rollback only reaches the two most recent deploys. | Not enough for dependable rollback. | The pipeline rolls back by redeploying the previous image digest through the API, with no depth limit. |
| No OIDC federation for the Render API. | A Render API key must be stored as a secret. | The key lives in GitHub environment secrets and is only released to a job after the environment rules pass. |

## GitHub free tier (public repository)

| Feature | Status |
|---|---|
| GitHub Actions minutes | Unlimited for public repositories |
| Environment protection rules with required reviewers | Free for public repositories |
| CodeQL code scanning, dependency review, secret scanning | Free for public repositories |
| Native arm64 runners (`ubuntu-24.04-arm`) | Free for public repositories |
| GitHub Container Registry | Free for public packages |
| GitHub Pages | Free for public repositories |

## Phase 0 spike results

The spike pushed a tiny multi-arch image to GHCR and drove the Render API from a workflow. Evidence: [spike build run](https://github.com/devwithvino/cicd_demo/actions/runs/38016753085) and [spike deploy run](https://github.com/devwithvino/cicd_demo/actions/runs/38017325980).

| Question | Result | Detail |
|---|---|---|
| Can GHCR images be pulled without credentials? | Yes | An anonymous pull of the manifest returned HTTP 200. Render needs no registry credential. |
| Does the deploy API accept an image digest? | Yes | `POST /v1/services/{id}/deploys` with `imageUrl` set to `image@sha256:...` went live in about 30 seconds. |
| Does Render pick the amd64 image from a multi-arch manifest? | Yes | The deploy record shows the requested index digest as `ref` and the resolved amd64 manifest digest as `sha`. |
| Does the running service prove which build is live? | Yes | `/version` returned the exact commit SHA baked into the image. |
| Does the service preview API work on the free plan? | Yes | `POST /v1/services/{id}/preview` created a free preview with its own `onrender.com` URL. |
| Can a preview's environment variables be changed after creation? | Yes | `PUT /v1/services/{previewId}/env-vars/{key}` updated the value. |
| Can a preview be deleted through the API? | Yes | `DELETE /v1/services/{previewId}` returned HTTP 204. |
| Can free web services reach Key Value? | Yes | `/readyz` on the free api and worker services returned ready over the internal connection string. A full job round trip passed in production. |
| Does blueprint sync overwrite a pipeline deploy? | Yes, for changed services | Pushing a `render.yaml` change redeployed the affected service from the tag in the blueprint (trigger `blueprint_sync`). See the mitigation below. |

### Blueprint sync mitigation

A sync redeploys whatever tag `render.yaml` names. If that tag were `main`, an infrastructure change could push an unapproved build into production and bypass the approval gate. So every environment has its own moving tag, `staging` and `production`. The pipeline moves an environment tag only after that environment's smoke test passes, by retagging the verified digest without rebuilding it. `render.yaml` references these environment tags, so a sync can only ever redeploy an image that already passed in that environment.

### Other platform notes

- Render appends a random suffix to a service subdomain when the plain name is taken. The staging API lives at `shipyard-api-staging-e87x.onrender.com`. Service URLs are stored as GitHub environment variables, so workflows never guess them.

### Notes for the real pipeline

- Previews are created with `autoDeploy` on. Image-backed services only deploy when asked, so this is harmless, but the pipeline sets it explicitly.
- Deploy status moves from `update_in_progress` to `live`. Failure states end in `failed`, `canceled` or `deactivated`.
- Rollbacks need the previous image to remain in GHCR, so the image cleanup job never deletes digests that are still referenced by a release.
