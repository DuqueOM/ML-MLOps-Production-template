# Security baselines

The May 2026 audit (HIGH-1) flipped the IaC scanners and `trivy` in
`.github/workflows/validate-templates.yml` from `soft_fail: true` to
**hard-fail**. To prevent legitimate, accepted findings from blocking
unrelated PRs, the workflow consults the per-tool baseline files in this
directory.

| Tool | File | Format |
| ------ | ------ | -------- |
| trivy config (IaC) | `trivy-config.trivyignore` | plain ignore list, one id per line, `# expiry:` above or inline (ADR-046) |
| Checkov | `checkov.yml` | Checkov config (skip-check + soft-fail-on lists) |
| Trivy | `.trivyignore` | One CVE-ID per line; `# rationale` comments allowed |

## Adding a finding to the baseline

1. **Confirm the finding cannot be fixed**: a vendor-side CVE without a
   patched release, an IaC pattern explicitly required by another invariant,
   or an upstream-only false positive.
2. **Open an ADR or issue** documenting the rationale and the expiry date.
   Baseline entries are time-bounded; the goal is zero baseline by `v1.0.0`.
3. **Add the entry** with a `# expiry: YYYY-MM-DD` annotation **adjacent**
   to the entry. Two accepted styles:

   ```yaml
   # checkov.yml
   exclude:
     # expiry: 2026-08-01  reason: ADR-024 §"Review"
     - "AWS001"
   ```

   ```text
   # .trivyignore
   CVE-2026-12345  # expiry: 2026-08-01  vendor advisory: GHSA-xxxx
   ```

4. **Update `docs/audit/baseline-review.md`** (next quarterly review).

The `expiry:` annotation is enforced by
`scripts/check_baselines_expiry.py`, which runs as the
`security-baseline-expiry` job in
`.github/workflows/validate-templates.yml`. CI fails when:

- an entry is missing the `# expiry: YYYY-MM-DD` annotation, OR
- the annotated date is in the past.

Both failure modes have a clear resolution path: extend the expiry
with a fresh ADR justification, OR remove the entry by fixing the
underlying issue.

## Removing a finding

When a CVE is patched, an ADR closes, or the upstream resource is fixed,
remove the entry from the baseline file. CI then enforces it as a regular
finding on the next run.

## Why hard-fail matters

Soft-fail produces a green CI badge that lies. A reviewer reading the badge
believes the IaC is clean when in reality CRITICAL Terraform findings or
HIGH CVEs in container base layers are being ignored. The baseline files
make every accepted finding **explicit, dated, and reviewable**.
