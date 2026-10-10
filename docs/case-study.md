# Case study: from manual releases to a self verifying pipeline

Shipyard is a reference project: a small three service application whose real product is its delivery pipeline. This case study describes what the pipeline replaces and what it measurably delivers. Every number below was produced by the pipeline itself and can be checked on the [status page](https://devwithvino.github.io/cicd_demo/) or in the linked runs.

## The starting point: what a manual release involves

A typical team without automation ships a change like this one by hand. Each line is a step a person performs and can get wrong:

| # | Manual step | What can go wrong |
|---|---|---|
| 1 | Run linters and tests for three services in three languages | Skipped under time pressure |
| 2 | Scan for leaked secrets and vulnerable dependencies | Rarely done at all |
| 3 | Build three container images, for two CPU architectures | Built from a dirty working copy |
| 4 | Scan the images for vulnerabilities | Rarely done at all |
| 5 | Tag and push the images | Wrong tag, or a tag that is later overwritten |
| 6 | Deploy to staging, one service at a time | Services briefly run mismatched versions |
| 7 | Click through staging to check it works | Checks differ from person to person |
| 8 | Ask someone to approve production | Approval happens in chat, with no record |
| 9 | Rebuild or retag for production | Production gets a different build than staging tested |
| 10 | Deploy to production | Same as step 6 |
| 11 | Check production | Same as step 7 |
| 12 | Write release notes and tell the team | Forgotten |
| 13 | If something breaks: find the previous version and redeploy it | Under pressure, at the worst moment |
| 14 | Write up what happened | Rarely done |

Most of these steps depend on one person's memory and care. The riskiest ones, the security scans, the identical build in staging and production, and a fast rollback, are exactly the ones most often skipped.

## What the pipeline does instead

Every step above now happens on every change, the same way every time, with no manual action except one approval click for production.

| Manual step | Automated as | Where |
|---|---|---|
| 1, 2 | Lint, type check and test in Go, Python and TypeScript; gitleaks, CodeQL, dependency review | [`ci.yml`](../.github/workflows/ci.yml), [`security.yml`](../.github/workflows/security.yml) |
| 3, 4, 5 | Build once for amd64 and arm64, Trivy gate, SBOM, keyless signature and SLSA provenance, immutable digests | [`_build.yml`](../.github/workflows/_build.yml) |
| 6, 7 | Deploy all services in parallel, smoke test with a real job, Sentry error gate | [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml) |
| 8 | GitHub environment approval with a named reviewer, announced in Slack | [`deliver.yml`](../.github/workflows/deliver.yml) |
| 9, 10, 11 | The identical, signature verified digests go to production; same checks | [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml) |
| 12 | Versioned GitHub Release with changelog, SBOMs and provenance; Slack summary | [`deliver.yml`](../.github/workflows/deliver.yml) |
| 13 | Automatic rollback to the previous digests, verified by the same smoke test | [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml) |
| 14 | Incident issue with a timeline, opened automatically | [`_deploy-render.yml`](../.github/workflows/_deploy-render.yml) |

## Measured results

From the first day of operation (observed window: one day, 2026-10-10):

| Measure | Result | DORA rating |
|---|---|---|
| Production deploys | **16**, all successful, across 12 versioned releases | |
| Deployment frequency | 16 per day | Elite |
| Lead time, commit to production | **10m 08s** median, including the human approval | Elite |
| Pipeline time, excluding the approval wait | **5m 24s** median | |
| Change failure rate | **0 of 16** production deploys | Elite |
| Failed staging deploys that never reached production | **4** (pipeline setup issues and one slow platform start, not application bugs) | |
| Time to restore | **28s** and **39s** in two rollback drills, from failure detected to service verified | Elite |

Supporting numbers from the same period:

| Measure | Result |
|---|---|
| Build: 3 services, 2 architectures, scanned, signed and attested | 2m 30s median over 29 builds |
| Production deploy plus smoke test | about 50 seconds typical |
| CI pass rate | 98.5% over 66 runs |
| Kubernetes performance gate (k6, 10 users) | read p95 7 ms, write p95 8 ms, 0% errors |
| API container image | 22 MB, distroless, non root |
| Hosting cost | $0 |

## Problems the pipeline caught

These were real, not staged, except where marked as a drill:

- **A leaked credential.** A private key file was committed by mistake. The secret scan flagged it about two minutes after the push; the key was revoked and the incident documented.
- **Vulnerable base images.** The image scan found 11 fixable HIGH vulnerabilities in tools bundled with the Node.js and Python base images. Removing those tools from the runtime images cleared all of them.
- **Log injection.** Code scanning found that a client supplied header reached the logs unchanged. Fixed in two services before release.
- **A release that would not start in time.** Render took 12.5 minutes to bring one staging deploy live. The pipeline treated it as failed and kept the previous version serving; the hardening that followed is recorded in [incident #22](https://github.com/devwithvino/cicd_demo/issues/22).
- **Rollback drills.** A deliberately broken release that passes every health check but breaks job submission was shipped to staging twice. Both times the smoke test caught it, the previous version was restored and verified within 40 seconds, and Sentry recorded the error against the exact release.

## What a client gets from this approach

- **Speed without risk.** Many small releases a day, each one verified in staging and production by the same automated checks.
- **Evidence instead of trust.** Every production image can be traced to its source commit and build, verified with one command, and comes with a full parts list.
- **Fast, boring recovery.** Bad releases are undone in under a minute without anyone logging in.
- **Visibility for everyone.** A public status page with live health and delivery metrics, Slack messages for every release, approval and incident.
- **Low running cost.** The whole system here runs on free tiers. The same design scales to paid platforms without changing the pipeline.
