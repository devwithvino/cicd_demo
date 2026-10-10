# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** button on the [Security tab](https://github.com/devwithvino/cicd_demo/security/advisories/new). Do not open a public issue.

Include what you found, how to reproduce it and the impact you expect. You can expect an acknowledgement within three working days and a status update within seven.

## Supported versions

Only the latest release is supported. Fixes ship as a new release through the normal pipeline, which rebuilds, rescans and re signs every image.

## How this project protects itself

| Layer | Control |
|---|---|
| Source | Branch ruleset on `main`, required checks, squash merges only, secret scanning with push protection, gitleaks over the full history |
| Code | CodeQL for Go, Python, TypeScript and the workflows, fuzz tests for untrusted input |
| Dependencies | Dependency review on every pull request, Dependabot with a seven day cooldown, pinned actions and base images |
| Images | Trivy gate on fixable HIGH and CRITICAL findings, SBOM for every image, nightly re scan of running images |
| Release | Keyless cosign signatures, SLSA build provenance and SBOM attestations, deploys refuse unsigned images |
| Pipeline | Least privilege workflow permissions, environment scoped secrets, approval gates for production and infrastructure, zizmor workflow linting |

## Verifying a release

```bash
gh attestation verify oci://ghcr.io/devwithvino/shipyard-api@<digest> --repo devwithvino/cicd_demo
```
