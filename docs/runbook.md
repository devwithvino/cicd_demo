# Runbook

What to do when something goes wrong, and how to make routine changes. Commands assume the GitHub CLI is logged in to this repository.

## Rollback

There are three levels. Use the first one that applies.

### 1. Automatic (nothing to do)

Every deploy rolls itself back when its smoke test or the Sentry gate fails. The pipeline redeploys the images that were live before, verifies them with the same smoke test, opens an incident issue with a timeline and posts to Slack. Check the incident issue and the linked run, then fix the cause in a new pull request.

### 2. One click

For a problem found after a deploy succeeded: Actions, **rollback**, Run workflow.

- `environment`: the affected environment.
- `version`: leave `previous` to return to the release before the current one, or name a release such as `0.8.0`.
- `reason`: one sentence. It goes into the Slack message.

Production asks for approval. The rollback reuses the released, signed images, so nothing is rebuilt.

```bash
gh workflow run rollback.yml -f environment=production -f version=previous -f "reason=checkout errors after 0.9.0"
```

Releases older than 0.4.0 predate image signing and are refused by the deploy gate.

### 3. Emergency, without GitHub

If GitHub Actions itself is unavailable: Render dashboard, open the service, **Events** or **Deploys**, pick the last good deploy and choose **Rollback**. Render only keeps the two most recent deploys for this, so prefer the one click path whenever it works. Afterwards, run the `deploy-manual` workflow with the same version so the environment tag and the status page match reality again.

## Incidents

1. Open the incident issue the pipeline created, or create one with the label `incident`.
2. Check Slack and the run linked from the issue: which check failed (smoke test, Sentry gate, deploy timeout).
3. Check Sentry for errors in that release and environment (the incident links to the filtered view).
4. Confirm the service is healthy again: the status page or `/version` on the web service.
5. Fix the root cause in a pull request, add a test that would have caught it, and close the issue with a short note.

Known platform behaviour: free Render instances can take more than ten minutes to start. The pipeline waits up to 20 minutes and Render keeps the previous version serving meanwhile.

## Rotating secrets

Rotate on a schedule (every 90 days is a good default) and immediately if a secret may have leaked. Rotation never needs a deploy: workflows read secrets when they start.

| Secret | Where it lives | How to rotate |
|---|---|---|
| Render API key | `RENDER_API_KEY` in the `preview`, `staging` and `production` environments | Render, Account Settings, API Keys: create a new key, then set it in each environment, then delete the old key in Render |
| Slack webhook | Repository secret `SLACK_WEBHOOK_URL` | Slack app, Incoming Webhooks: add a new webhook, set the secret, remove the old webhook |
| Sentry token | Repository secret `SENTRY_AUTH_TOKEN` (personal token: event:read, project:read, project:releases, org:read) | Sentry, User Settings, Personal Tokens: create, set, then revoke the old one |
| Release App key | Repository secret `RELEASE_APP_PRIVATE_KEY` | GitHub App settings, Private keys: generate a new key, set the secret, delete the old key |

Set a secret without it ever touching disk:

```bash
gh secret set RENDER_API_KEY --env production --repo devwithvino/cicd_demo
```

Never save key files inside the repository folder. Key patterns are ignored by git and secret scanning runs on every push, but the safest key is one that never comes near the repository.

## Adding a new service

The pipeline is built around a list of services. A new service, for example `notifier`, touches these places:

1. **Code**: `services/notifier/` with a multi stage `Dockerfile` (non root user, `/healthz`, `/version`, `/metrics`), tests and a lint setup.
2. **CI**: a job in [`ci.yml`](../.github/workflows/ci.yml) and a path filter for it; a matrix entry in the hadolint job.
3. **Build**: add it to the `service` matrices in [`_build.yml`](../.github/workflows/_build.yml). The digest map then includes it automatically.
4. **Deploy**: a service per environment in [`render.yaml`](../render.yaml), its service ID and URL as environment variables, and the name in the `SERVICES` list of [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml) and [`platform.yml`](../.github/workflows/platform.yml).
5. **Previews**: the base service ID in the `preview` environment and the wiring in [`render_preview.py`](../scripts/render_preview.py).
6. **Kubernetes**: an entry in the service table of the [Helm chart](../deploy/helm/shipyard/templates/services.yaml), resources and replicas in `values.yaml`, and a network policy rule.
7. **Local**: a service in [`docker-compose.yml`](../docker-compose.yml) and a scrape target in [`prometheus.yml`](../deploy/observability/prometheus.yml).
8. **Checks**: extend [`smoke_test.py`](../scripts/smoke_test.py) if the service has its own health contract, and the Dependabot config for its package ecosystem.

Open everything as one pull request. The preview environment and the Kubernetes job prove the wiring before anything reaches staging.
