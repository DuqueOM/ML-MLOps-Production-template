# ADR-046 — Replace archived tfsec with Trivy config for Terraform IaC scanning

- **Status**: Accepted
- **Date**: 2026-09-05
- **Deciders**: template maintainer
- **Amends**: ADR-024 §HIGH-1 (which flipped tfsec from `soft_fail` to hard-fail)
- **Related**: ADR-042 (edge protection), `.security-baselines/README.md`,
  `docs/audit/baseline-review.md`

## Context

The Terraform IaC gate in the `Self-audit` job ran **tfsec v1.28.14**, pinned
because tfsec is archived. The workflow said so itself:

```
# tfsec archived; pinned to last working release (v1.28.14).
# TODO: migrate to trivy config (tfsec successor) per ADR-TBD.
```

The binary announces it on every run: *"tfsec is joining the Trivy family …
our engineering attention will be directed at Trivy going forward."*

Two consequences, and the second is the one that mattered:

1. **No new rules, ever.** Every Terraform feature adopted after the archive
   date has no coverage. The HIGH gate erodes silently as the modules grow.
2. **Three HIGH findings were suppressed, and two of them existed only
   because tfsec could not evaluate the HCL.** `google-gke-enable-master-networks`
   and `google-gke-metadata-endpoints-disabled` were tool limitations, not
   risks — the controls are present and correct. Suppressing a *tool defect*
   in a frozen tool means the suppression can never be resolved, only
   renewed. `docs/audit/baseline-review.md` recorded all three with a
   2027-01-01 expiry, which is a date standing in for a decision.

The `ADR-TBD` in that TODO is this document.

## Measurement

Run before deciding, on this repository, at the gate's own threshold
(`HIGH,CRITICAL`), with tfsec v1.28.14 and Trivy 0.71.0:

| Scanner | Suppressions removed | GCP | AWS |
|---|---|---|---|
| tfsec v1.28.14 | yes | **4** | 0 |
| Trivy 0.71.0 `config` | yes | **1** | 0 |

The four tfsec findings are the three suppressed checks
(`metadata-endpoints-disabled` fires twice, once per node pool). Under Trivy:

| tfsec check | Under Trivy | Why |
|---|---|---|
| `google-gke-enforce-pod-security-policy` | **gone** | PSP was removed in Kubernetes 1.25; Trivy dropped the check. Suppressing it was compensating for a rule that should not have existed. |
| `google-gke-metadata-endpoints-disabled` (×2) | **gone** | Trivy correlates `google_container_node_pool` resources to their cluster. tfsec only inspected `node_config` on the cluster, which this module does not have (`remove_default_node_pool = true`). |
| `google-gke-enable-master-networks` | **survives** as `GCP-0061` | Neither tool evaluates `dynamic` blocks. `master_authorized_networks_config` is a `dynamic` block at `compute.tf:38`; the finding fires against the cluster at `compute.tf:10`. |

Below the gate threshold Trivy reports 5 MEDIUM and 8 LOW across the five
modules. They do not block, and triaging them is separate work.

**Two of three suppressions dissolve. Three become one.**

### Amendment (2026-09-05): the third one dissolved too, and it was not a false positive

The surviving suppression was carried on the grounds that the HCL is correct
and only the scanner cannot see it. Re-reading its justification while
closing this ADR out, one clause did not hold:

> Environment overlays MUST supply non-empty `master_authorized_networks`
> for staging/prod (enforced by the variable validation rule in
> `variables.tf`).

**There is no such validation rule**, and no overlay or tfvars file sets the
variable anywhere. It defaults to `[]`, the `dynamic` block therefore never
rendered, and GKE's default with no authorized-networks block is *no
restriction*. Harmless while `enable_private_endpoint = true` — the default —
and a publicly reachable control plane the moment an adopter takes the
documented dev opt-out and sets it false.

So `GCP-0061` was pointing at a real gap in that path, justified by a
compensating control that had never been built. The module was fixed rather
than the finding re-suppressed: the block is now unconditional (an empty list
means "enabled, nothing allowed" instead of "not configured"), and a
`precondition` on the cluster rejects the dangerous pairing at plan time.

`.security-baselines/trivy-config.trivyignore` is now empty. **Three
suppressions become zero**, and the 2027-01-01 review has nothing left to
re-justify.

## Decision

Replace tfsec with `trivy config` in the `Self-audit` job.

1. **One recursive scan** over `templates/service/infra/terraform` reaches
   all five root modules. tfsec only ever ran on `gcp` and `aws` — the two
   bootstrap layers and the Cloudflare edge module were never scanned. This
   closes the same gap #78 closed for `terraform validate`.
2. **Same pinned action** (`aquasecurity/trivy-action`, already used for the
   filesystem scan) rather than a new binary install. Note that the action
   does not leave `trivy` on `PATH`, so a plain `run:` step would fail.
3. **`.security-baselines/trivy-config.trivyignore`** carries the single
   surviving suppression, in the same explicit/dated/reviewable shape as
   every other file in that directory.
4. **`.security-baselines/tfsec.yml` is deleted.** Keeping a config for a
   tool that no longer runs is a stale claim of the kind this repo keeps
   finding.

### Expiry stays with our own gate, not with Trivy

Trivy's YAML ignore format accepts an `expiredAt:` field. **It does not
honour it.** Measured here: an entry dated `2020-01-01` still suppressed its
finding, in all three date formats tried (`2020-01-01`, `"2020-01-01"`,
`2020-01-01T00:00:00Z`), with nothing on stderr.

Delegating expiry to the tool would therefore have produced exactly the
failure `.security-baselines/` exists to prevent: a suppression outliving
its justification while the gate reports green.
`scripts/check_baselines_expiry.py` remains the authority, and the plain
`.trivyignore` format is used so one parser covers every baseline file.

### The guard was extended, not just re-pointed

`check_baselines_expiry.py` named its three baseline files literally. Under
that shape, replacing `tfsec.yml` with a new file would have left the new
file **unwatched while the gate reported green** — the same defect class as
the scan-scope failures in #79, #86 and #89. It now discovers every file in
`.security-baselines/` and treats an unrecognised format as a failure rather
than a silent skip. Its id pattern also required a four-digit year followed
by a second number, so misconfiguration ids (`GCP-0061`) matched nothing.

## Consequences

- The Terraform gate runs on a maintained scanner and gains rules over time
  instead of freezing.
- IaC coverage widens from two root modules to five.
- Suppressions drop from three to one, and the survivor is a genuine
  static-analysis limit rather than a tool defect.
- `docs/audit/baseline-review.md`'s 2027-01-01 review now has one entry
  instead of three, and it is the one that will still be true then.
- The `Self-audit (gitleaks + tfsec + checkov + trivy fs)` job **kept its
  name** in this change despite no longer running tfsec. That name is one of
  the six required status checks in the ADR-026 ruleset; renaming it in the
  same change would have blocked the very PR making the change, because the
  required context would never report.

  **Resolved since**: the rename was carried out as the three-step ruleset
  transition this ADR anticipated, and the job is now
  `Self-audit (secrets + IaC + supply chain)` — named for the classes of
  check rather than the tools, so the next tool swap touches no contract.
  The procedure is written down in `docs/governance/branch-protection.md`
  §"Renaming a required check".
- MEDIUM and LOW findings are visible but not enforced. Raising the threshold
  is a separate decision with its own triage cost.

  **Done, 2026-09-05.** The triage found that three of the five MEDIUM were
  real: two node pools running as the default Compute Engine service account
  (`GCP-0050`, a D-31 violation — see ADR-017 §Amendment) and a project-wide
  `roles/iam.serviceAccountUser` grant whose comment claimed a condition that
  did not exist (`GCP-0011`). Both fixed in the module. The remaining two are
  object versioning on append-only access-log buckets, accepted with a dated
  justification. The gate now runs at `CRITICAL,HIGH,MEDIUM`.

  LOW stays out: 8 findings whose triage has not been done. An unenforced
  threshold is honest about that in a way a suppressed finding is not.

  The scaffolded service's `ci-infra.yml` stays at `CRITICAL,HIGH`. The higher
  bar here is affordable because this repo has `.security-baselines/` and an
  expiry gate; a generated service has neither, and a MEDIUM gate with no way
  to record an accepted finding trains adopters to delete the step.

## Alternatives considered

**Extend the three expiries to a later date.** Zero cost today, but it
renews suppressions for defects in a frozen tool — they can never be
resolved, only rolled forward, which trains reviewers to bump dates without
reading them. Rejected: it treats the symptom and preserves the cause.

**Stagger the three expiries.** Reduces the risk of a bulk extension when
all three come due at once. A real improvement over the status quo, but
still leaves the archived scanner in place. Rejected as insufficient, though
it was the fallback had the measurement gone the other way.

**Lower `minimum_severity`, or return to `soft_fail`.** Removes the problem
by removing the control, reverting ADR-024 §HIGH-1. Rejected.

**Inline `#tfsec:ignore` comments beside each resource.** Puts the
suppression next to the code it excuses, which reads well. But it stays tied
to the archived tool and gives up the central dated register that
`check_baselines_expiry.py` enforces. Rejected.

**Run both scanners for a transition period.** The usual safe play. Rejected
here because the measurement is cheap, complete and already done: one HIGH
finding across five modules, fully explained. Carrying two IaC scanners
would double the maintenance surface to hedge a risk that has already been
quantified.
