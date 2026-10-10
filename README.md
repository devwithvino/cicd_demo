# Shipyard

**Build once. Containerize once. Deploy anywhere. No manual steps. Zero cost.**

Shipyard is a reference delivery pipeline. A small microservices app (Go API, Python worker, TypeScript dashboard) travels from a `git push` to a live, monitored, rollback-capable deployment, fully automated with GitHub Actions and hosted on free tiers.

> Work in progress. The full README with architecture diagrams, live links and status badges arrives in Phase 4.

## What this project proves

- Every change is linted, tested, scanned and signed before it can ship.
- One container image is built per change and the exact same digest is promoted from staging to production.
- Production needs a human approval. Everything else is automatic.
- Failed releases roll back on their own, and the team is notified with a clear summary.
- The same images run on Render, on Kubernetes (Kind) and on a laptop with Docker Compose.

## Repository layout

| Path | Purpose |
|---|---|
| `services/` | The three application services |
| `deploy/` | Helm chart and observability config |
| `infra/` | Terraform for repository settings and environments |
| `.github/` | Workflows, composite actions and automation config |
| `scripts/` | Smoke tests, metrics and lint helpers |
| `docs/` | Case study, runbook, demo script and decision records |

## License

MIT, see [LICENSE](LICENSE).
