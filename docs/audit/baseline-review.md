# Security Baseline Review

**Cadence**: quarterly
**Owner**: `security_owner` (see `templates/config/company_context.example.yaml`)
**Enforcement**: `scripts/check_baselines_expiry.py` + the `security-baseline-expiry` job in `.github/workflows/validate-templates.yml`
**Procedure**: `.security-baselines/README.md` step 4
**Related**: ADR-024 §Review (the decision that made tfsec/checkov/trivy hard-fail with explicit baselines)

## Why this document exists

`.security-baselines/README.md` has instructed reviewers to "update
`docs/audit/baseline-review.md` (next quarterly review)" since the
baselines were introduced. The document did not exist, so three
HIGH-severity suppressions had a written justification in a YAML comment
and no review record anywhere.

A suppression without a review record is indistinguishable from a
suppression nobody remembers making. This is that record.

## Review — 2026-09-04

### What the review found first: the gate was not watching

`scripts/check_baselines_expiry.py` reported `OK — no expired or
unannotated entries` while three HIGH GKE checks sat suppressed. It was
not lying about the entries it saw; it saw none.

Its `yaml_entry` pattern required a suppression id to begin with an
uppercase letter, which matches checkov ids (`CKV_AWS_18`) and misses
every tfsec id (`google-gke-enable-master-networks`). The file was
scanned, zero entries matched, and zero expired entries is a pass.

Two changes were needed, because the obvious one is wrong on its own:

1. The pattern is now case-insensitive.
2. Matching lowercase alone would have swept in `framework: [terraform,
   kubernetes, dockerfile]` from `checkov.yml`, which is a sequence but
   not a suppression. The scanner is now **block-aware** and only treats
   items under `exclude:` / `skip-check:` as entries — which is what the
   code's own comment had claimed since it was written.

The three entries also carried `Review-by: 2027-01`, a format the gate
does not parse; the gate requires `# expiry: YYYY-MM-DD` on the entry line
or the line directly above it. They were normalised, keeping the original
prose justification intact above the annotation.

Verified after the change: the gate reports all three today (in-date), and
`--as-of 2027-06-01` fails all three as expired.

### Suppressions in force

All three are tfsec exclusions. `checkov.yml` carries `skip-check: []` —
no suppressions — and no trivy ignore file is present.

| Check | Severity | Why suppressed | Compensating control | Expiry |
|---|---|---|---|---|
| `google-gke-enforce-pod-security-policy` | HIGH | PodSecurityPolicy was deprecated in Kubernetes 1.21 and **removed** in 1.25. GKE REGULAR channel runs 1.27+, so enabling it would fail the apply outright. | Pod Security Standards enforced via namespace labels in every overlay (D-29, `templates/service/k8s/overlays/*/namespace.yaml`) | 2027-01-01 |
| `google-gke-enable-master-networks` | HIGH | `master_authorized_networks_config` **is** present, as a `dynamic` block. tfsec v1.28 does not evaluate dynamic blocks and reports it absent even when the HCL is correct. | The block is real; staging and prod must supply a non-empty `master_authorized_networks`, enforced by a variable validation rule in `variables.tf` | 2027-01-01 |
| `google-gke-metadata-endpoints-disabled` | HIGH | tfsec reads `node_config.metadata` on `google_container_cluster` only. This module uses `remove_default_node_pool = true` plus two `google_container_node_pool` resources, so the cluster has no `node_config` and the attribute lives on the pools. | Workload Identity on both pools (alone sufficient against metadata SSRF) **plus** `disable-legacy-endpoints = "true"` on each pool | 2027-01-01 |

Every one is a **tool limitation, not an accepted risk**: in all three
cases the control exists and tfsec cannot see it. That distinction is the
reason the expiries are tied to the tfsec → trivy migration rather than to
a risk-acceptance window.

### Verdict

All three suppressions remain justified. No new suppressions were added.
No entry was extended.

## Review — 2026-09-05 (ADR-046)

The 2026-09-04 review closed with "the trigger to close them early is the
tfsec → trivy migration". That migration was measured and executed the next
day; see ADR-046 for the full comparison.

**Two of the three suppressions dissolved rather than being renewed:**

| Suppression | Outcome |
|---|---|
| `google-gke-enforce-pod-security-policy` | **removed** — Trivy has no PSP check; PSP was deleted from Kubernetes in 1.25 |
| `google-gke-metadata-endpoints-disabled` | **removed** — Trivy correlates node pools to their cluster; tfsec could not |
| `google-gke-enable-master-networks` | **survives** as `GCP-0061` — neither tool evaluates `dynamic` blocks |

Suppressions in force: **one**, in
`.security-baselines/trivy-config.trivyignore`, expiring 2027-01-01.
`.security-baselines/tfsec.yml` is deleted.

Also worth recording: Trivy's own `expiredAt:` ignore field is **not
honoured** by 0.71.0 — an entry dated 2020-01-01 still suppressed its
finding, silently. `scripts/check_baselines_expiry.py` remains the expiry
authority, and it now discovers baseline files instead of naming three of
them literally, so a future format swap cannot leave a file unwatched.

## Review — 2026-09-05 (second entry, same day): the last suppression is gone

Closing ADR-046 out meant re-reading the one surviving justification, and a
clause in it did not hold:

> Environment overlays MUST supply non-empty `master_authorized_networks`
> for staging/prod (enforced by the variable validation rule in
> `variables.tf`).

There was no such rule, and nothing sets the variable anywhere — it defaults
to `[]`. The `dynamic` block therefore never rendered, and GKE with no
authorized-networks block applies *no restriction*. Safe while
`enable_private_endpoint = true` (the default); a public control plane with
no allowlist as soon as an adopter takes the documented dev opt-out.

`GCP-0061` was not a false positive. It was pointing at a real gap, held open
by a compensating control that had never been built.

**Fixed in the module rather than re-suppressed:**

- the authorized-networks block is now unconditional, so an empty list means
  "enabled, no external CIDR allowed" instead of "not configured";
- a `precondition` on `google_container_cluster.gke` rejects
  `enable_private_endpoint = false` together with an empty list, at plan
  time. Verified across all three combinations, including that the safe ones
  still pass.

**Suppressions in force: zero.**
`.security-baselines/trivy-config.trivyignore` is empty, which is the
intended steady state.

### What this says about the review itself

The 2026-09-04 review recorded all three as "tool limitations, not accepted
risks" and I wrote that in good faith from the justifications on file. Two of
the three were. The third's justification asserted an enforcement that did
not exist, and no review had checked it — because reviewing a suppression had
meant reading its rationale, not verifying it.

Step 3 of the procedure below now says to confirm the compensating control
exists **in the file the justification names**. That step is what would have
caught this, and it is why it is written the way it is.

## Review — 2026-09-05 (fourth entry): the MEDIUM triage, and two acceptances

ADR-046 had deferred the sub-threshold findings as "separate work". Doing it
changed the picture: **three of the five MEDIUM were real.**

| Finding | Verdict |
|---|---|
| `GCP-0050` ×2 — GKE node pools with no `service_account` | **Real.** Nodes ran as the default Compute Engine service account, typically `roles/editor` project-wide. A D-31 violation inside the module that implements D-31. Fixed: a sixth identity, `nodes`, with Google's documented minimum. |
| `GCP-0011` — project-wide `roles/iam.serviceAccountUser` | **Real.** The comment claimed "Scoped via condition"; there was no condition block, so CI could impersonate any service account in the project. Fixed: three per-account bindings (`deploy`, `runtime`, `nodes`). |
| `GCP-0078` / `AWS-0090` — access-log buckets not versioned | **Accepted.** Append-only sinks, already lifecycle-bounded. Versioning guards against overwrite and modification of existing objects, neither of which is a failure mode here. Dated to 2027-03-05. |

Note the distinction the previous review learned to make: the first two are
**defects**, the last is an **accepted risk** where the check is correct in
general and does not apply to this object lifecycle. Only the third kind
belongs in a baseline.

The gate now runs at `CRITICAL,HIGH,MEDIUM`. It ran at HIGH, which is why
these sat in the log for two releases being enforced by nothing.

### Third instance of the same pattern

`GCP-0011` makes it three: a comment asserting a control that was never
built, surviving because reviewing meant reading it.

1. tfsec's suppression cited a `variables.tf` validation rule — none existed.
2. `check_baselines_expiry.py` claimed to read `exclude:` blocks — it filtered
   on uppercase ids and saw none.
3. `ci_sa_user` claimed an IAM condition — the block was absent.

**A comment asserting that a control exists is a checkable claim, in exactly
the way a path is.** Nothing in this repo verifies that class of claim. That
is the open structural gap this review leaves behind, and it is a bigger
finding than any of the three.

## Review — 2026-09-07 (fifth entry): the LOW triage, and the threshold reaches the floor

The MEDIUM review left LOW unenforced with the reasoning that "an unenforced
threshold is honest about untriaged findings in a way a suppressed one is
not". True, and still an evasion: *"we have not looked"* is a description,
not a decision. **Seven of the eight LOW findings were real.**

| Finding | Verdict |
|---|---|
| `GCP-0066` ×4 — live buckets without customer-managed encryption | **Real.** `models`, `data`, `mlflow_artifacts` and `logs` held Google-managed keys while the *bootstrap state bucket* has had CMEK since ADR-015. The asymmetry was backwards: the state file was better protected than the models and training data it describes. Fixed with a `storage` key on the existing ring. |
| `GCP-0054` ×2 — node image type not pinned | **Real.** COS is GKE's current default, which is why pinning matters: a default is not a decision, and inheriting it means a future change lands a different node OS without anyone choosing it. |
| `GCP-0051` — cluster without resource labels | **Real, minor.** Every bucket, key and service account in the module carries them; the cluster did not, so cost attribution had a hole exactly where the spend is. |
| `AWS-0089` — bootstrap state bucket without access logging | **Real.** Versioned, encrypted and public-access-blocked, and nothing recorded *who read it*. For a Terraform state file that is the interesting question. Implemented rather than accepted — the module has no CloudTrail, so there was no compensating control to point at. |

### Fixing a finding is not free of findings

Adding the access-log bucket to close `AWS-0089` introduced **three new
findings**, one of them HIGH:

- `AWS-0132` (HIGH) — SSE-S3 instead of a customer-managed key. Fixed: the
  bucket uses the existing bootstrap CMK with S3 Bucket Keys, which S3 has
  supported for access-log delivery since 2023.
- `AWS-0090`, `AWS-0089` on the new bucket itself — accepted, below.

Worth recording plainly: a new resource inherits every check that applies to
its type. "Close the finding" and "reduce the finding count" are not the same
operation, and the second is the wrong goal.

### Accepted, with their breadth stated

Four residual findings, all on **log-sink buckets**: versioning
(`GCP-0078`, `AWS-0090`) and self-logging (`AWS-0089`). Append-only,
write-once, lifecycle-bounded. Versioning guards against overwrite of
existing objects, which is not a failure mode here; self-logging has no fixed
point, because the log bucket's log bucket would need one too.

The baseline entries now state a limitation the earlier ones did not: the
plain ignore format suppresses a check id **repo-wide**, not per resource. So
each entry carries a review question about *which* buckets the check fires
on, not merely whether the justification still reads well. Trivy's YAML
format would scope by path and is not used, because its sibling `expiredAt:`
field is silently ignored (ADR-046) and one parser over one format is worth
more here than per-path precision on a four-entry file.

### The gate reaches the floor

`CRITICAL,HIGH,MEDIUM,LOW`. It walked up as the triage was done, never ahead
of it.

**Of the 13 findings that sat below a threshold across the two reviews, 10
were real defects.** "Below the threshold" predicted nothing about whether a
finding mattered. That is the argument against selective gates, and it is
why this one is now exhaustive.

## Next review

**Due 2026-12-05** (calendar, one quarter out) and **2027-03-05** (when the
four log-sink acceptances expire).

Two questions for March, both written into the baseline entries themselves
and both properties to verify rather than rationales to re-read:

1. *Are all three log buckets still access-log-only?* The versioning
   acceptance rests entirely on the objects being append-only.
2. *Is the Terraform state bucket still logged?* That is the control the
   `AWS-0089` entry must not be allowed to hide — the entry exists to accept
   the log bucket not logging itself, not to accept the state bucket going
   unlogged.

## How to run a review

1. `python3 scripts/check_baselines_expiry.py` — confirms nothing is
   expired or unannotated today.
2. `python3 scripts/check_baselines_expiry.py --as-of <next quarter>` —
   shows what is about to come due.
3. For each entry still in force: confirm the compensating control still
   exists, in the file the justification names. A justification that
   points at a control that has since moved is a suppression with no
   backing.
4. Record the outcome as a new dated section in this file. Do not edit a
   previous review; the point of the record is that it accumulates.
