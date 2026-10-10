# Services, and the proof in this repository

Each service below is something this project demonstrates working, end to end, with links to where it lives.

| Service | What the client gets | Proof in this repository |
|---|---|---|
| **CI/CD pipeline design and build** | Every change linted, tested, built once and promoted to production by digest, with one approval click | [`deliver.yml`](../.github/workflows/deliver.yml), [`_build.yml`](../.github/workflows/_build.yml), [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml) |
| **Safe releases and automatic rollback** | Post deploy verification, rollback in under a minute, incident reports written automatically | [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml), [`demo-failure.yml`](../.github/workflows/demo-failure.yml), [incident #20](https://github.com/devwithvino/cicd_demo/issues/20) |
| **Supply chain security** | Secret scanning, code and dependency scanning, image scanning, SBOMs, keyless signing, SLSA provenance, deploys that refuse unsigned images | [`security.yml`](../.github/workflows/security.yml), [`SECURITY.md`](../SECURITY.md), [blocked pull request #2](https://github.com/devwithvino/cicd_demo/pull/2) |
| **Containers and Kubernetes** | Small, hardened, multi architecture images and a production ready Helm chart, proven on a real cluster on every change | [`services/*/Dockerfile`](../services), [`deploy/helm/shipyard`](../deploy/helm/shipyard), [`_kind-e2e.yml`](../.github/workflows/_kind-e2e.yml) |
| **Preview environments** | A live copy of the app for every pull request, linked on the pull request, cleaned up automatically | [`pr-preview.yml`](../.github/workflows/pr-preview.yml), [`render_preview.py`](../scripts/render_preview.py) |
| **Observability and error monitoring** | Sentry across services and the browser, a release gate on new errors, Prometheus metrics and a Grafana dashboard | [Error monitoring](../README.md#error-monitoring-with-sentry), [`deploy/observability`](../deploy/observability) |
| **Delivery metrics (DORA)** | A live status page with deployment frequency, lead time, change failure rate and time to restore | [Status page](https://devwithvino.github.io/cicd_demo/), [`dora_metrics.py`](../scripts/dora_metrics.py) |
| **Platform operations** | One click pause and resume, runbooks for rollback, secret rotation and onboarding new services | [`platform.yml`](../.github/workflows/platform.yml), [operations guide](operations.md), [runbook](runbook.md) |
| **Repository governance and automation** | Branch rules, required checks, Dependabot with safe auto merge, nightly re scans, OpenSSF Scorecard | [`dependabot.yml`](../.github/dependabot.yml), [`nightly.yml`](../.github/workflows/nightly.yml), [`scorecard.yml`](../.github/workflows/scorecard.yml) |
| **Cost optimised hosting** | A full delivery platform on free tiers, with every limit documented and designed around | [Free tier limits](free-tier-limits.md) |

## Typical engagements

- **Pipeline audit** (a few days): review an existing setup against the practices above and deliver a prioritised plan.
- **Pipeline build** (one to three weeks): implement build once, environments, approvals, rollback and notifications for the client's stack and platform.
- **Security hardening** (about a week): scanning gates, SBOMs, signing and branch protection on an existing pipeline.
- **Kubernetes enablement** (one to two weeks): container hardening, a Helm chart and cluster tests in CI.
