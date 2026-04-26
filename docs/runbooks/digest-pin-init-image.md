# Runbook — Pin the model-downloader init container by digest

**Audience:** Platform engineer bootstrapping a new environment.

**Why:** Audit R2 (PR-R2-2, ADR-016) closed the gap where the
init container `google/cloud-sdk:slim` (GCP) and
`public.ecr.aws/aws-cli/aws-cli:2` (AWS) lived outside the
signed/digest-pinned image chain. Production overlays must pin
this image by digest so the rendered manifest is reproducible
and Kyverno's signature-and-digest gate accepts it.

This runbook is the **operator step** that the CI lint references
when it warns: _"image refs not pinned by digest"_.

## Prerequisites

- `crane` (≥ 0.16) **OR** Docker installed locally.
  ```bash
  go install github.com/google/go-containerregistry/cmd/crane@latest
  # or
  brew install crane
  ```
- `gcloud auth configure-docker` (GCP) or `aws ecr get-login-password`
  (AWS) if either registry requires auth from your workstation.

## Steps

### 1. Resolve the current digest

GCP cloud SDK image:
```bash
crane digest gcr.io/google.com/cloudsdktool/google-cloud-cli:slim
# Outputs: sha256:abc123…
```

AWS CLI image:
```bash
crane digest public.ecr.aws/aws-cli/aws-cli:2
# Outputs: sha256:def456…
```

Copy the full `sha256:...` value to your clipboard.

### 2. Update the overlay

Edit the relevant overlay's `kustomization.yaml`:

```yaml
images:
  # …existing app image entry…
  - name: "cloud-cli-image"
    newName: "gcr.io/google.com/cloudsdktool/google-cloud-cli"   # GCP
    # newName: "public.ecr.aws/aws-cli/aws-cli"                  # AWS
    newTag: "slim"   # or "2" for AWS
    digest: "sha256:abc123…"   # paste here
```

Repeat for each environment overlay you operate
(`*-staging`, `*-prod`).

### 3. Validate locally

```bash
kustomize build templates/k8s/overlays/gcp-prod | grep '^[[:space:]]*image:'
```

Every `image:` line should end with `@sha256:...`. If any does
not, the CI lint will warn (`*-staging`) or (in PR-R2-3) hard-fail
(`*-prod`).

### 4. Commit + open a PR

```bash
git add templates/k8s/overlays/gcp-prod/kustomization.yaml \
        templates/k8s/overlays/aws-prod/kustomization.yaml
git commit -m "ops: pin cloud-cli-image init container by digest (PR-R2-2)"
```

PR title convention: `ops(prod): pin init container by digest <date>`.
Approver: Platform engineer with prod overlay merge rights.

## Rotation cadence

- **Recommended:** every 90 days (security-scan window) or when
  upstream pushes a CVE fix to the base image, whichever is sooner.
- **Trigger:** dependabot opens a PR against the overlay file when
  it detects a new digest for the pinned tag. (Configured in
  `.github/dependabot.yml`; verify the `package-ecosystem: docker`
  entry covers the overlay paths.)

## Out-of-scope

- Application image (`{service}-predictor`) digest pinning is
  handled automatically by `templates/cicd/deploy-common.yml`'s
  `Pin image to digest` step using the digest emitted by the
  build job. Do NOT pin it manually here.
- Kyverno signature verification on init images is queued for
  PR-R2-3 alongside the prod overlay neutralization.

## References

- ADR-014 §B2 — image digest pinning chain
- ADR-016 PR-R2-2 — audit R2 init/CronJob digest closure
- D-19 — supply chain integrity invariant
- `.github/workflows/validate-templates.yml` § _Image digest pinning_
