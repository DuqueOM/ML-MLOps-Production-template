---
paths:
  - "**/Dockerfile"
  - "**/docker-compose*.yaml"
  - "**/docker-compose*.yml"
---

# Docker Rules

## Invariants (D-11, D-19, D-29, D-30)
- **D-11** NEVER bake model artifacts into images — init container + emptyDir pattern
- **D-19** Unsigned images rejected in prod (Kyverno admission)
- **D-29** Containers run as non-root: `USER 65532`, no capabilities
- **D-30** Every prod image has a CycloneDX SBOM attestation (Cosign)

## Dockerfile structure
- Multi-stage build: builder → runtime
- Runtime base: `gcr.io/distroless/python3-debian12:nonroot` or `python:3.11-slim`
- `COPY --from=builder --chown=65532:65532 /app /app`
- Drop root: `USER 65532`
- Health probe: `HEALTHCHECK` optional (K8s probes are authoritative)
- No `CMD ["uvicorn", "--workers", "N"]` — always 1 worker (D-01)

## Build + sign + SBOM (CI/CD)
```bash
docker build -t ${IMG} .
syft packages ${IMG} -o cyclonedx-json > sbom.cdx.json
cosign sign --yes ${IMG}                                  # keyless OIDC
cosign attest --yes --type cyclonedx --predicate sbom.cdx.json ${IMG}
```

## Forbidden
- `FROM python:3.11` (use slim or distroless)
- `RUN pip install` without pinned requirements file
- `COPY . .` without `.dockerignore` (ships .git, tfstate, secrets)

See `AGENTS.md §D-11, D-19, D-29, D-30`, `.windsurf/rules/07-docker.md`,
`.windsurf/skills/security-audit/SKILL.md`.
