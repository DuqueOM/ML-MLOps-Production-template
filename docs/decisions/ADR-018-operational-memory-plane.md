# ADR-018: Operational Memory Plane

- **Status**: Proposed (Phase 0 — scope + non-goals + threat model)
- **Date**: 2026-04-28
- **Deciders**: @DuqueOM, AI staff engineer
- **Supersedes**: none
- **Related**: ADR-010 (Dynamic agent behavior),
  ADR-014 (Gap remediation plan, audit trail),
  ADR-016 (External audit R2 remediation),
  AGENTS.md (Audit Trail Protocol, Agent Permissions Matrix)

## Context

The template currently produces a rich but **siloed** evidence trail:

- `ops/audit.jsonl` — append-only operational decisions
- `drift_report.json`, `performance.json`, `champion_challenger.json`
  — per-run ML quality artifacts
- GHA step summaries + workflow artifacts
- GitHub issues tagged `audit`, `incident`, `quality-gate-failure`
- Postmortems in `docs/runbooks/postmortems/`
- ADRs in `docs/decisions/`

Each surface answers one question well. Cross-surface questions —
*"have we seen this drift pattern before?"*, *"did the last
champion-challenger A/B actually improve fairness?"*, *"which
remediation worked when this incident-class fired in staging?"* —
require a human to manually correlate evidence across at least 3
surfaces. The agent stack today CANNOT answer them.

This is the gap an Operational Memory Plane closes: a derived,
queryable layer over the existing evidence so agents (and humans)
can recall similar past situations BEFORE deciding.

The plane is explicitly **derived**, not authoritative. The systems
of record (audit.jsonl, MLflow registry, K8s deploy chain) remain
the source of truth.

## Decision

Adopt an **Operational Memory Plane** as a companion capability,
shipped in 7 phases. This ADR ratifies **Phase 0** only — scope,
non-goals, and threat model. Phases 1–6 will each have their own
ADR addendum or PR with measurable acceptance criteria before code
lands.

### What the plane IS

A typed, audited retrieval layer that:

- Normalizes existing evidence (audit entries, drift reports,
  postmortems, security findings) into a canonical `MemoryUnit`
- Stores units in PostgreSQL with `pgvector` for semantic search
  (single store; no separate vector DB)
- Stores raw evidence in cloud object storage (S3 / GCS) with
  pre-signed URLs for retrieval
- Exposes a small FastAPI surface for `/search`, `/contextual-recall`,
  `/incident-similarity`, `/feedback`
- Produces ADDITIONAL risk signals consumed by `risk_context.py`
  (e.g. `repeat_failure_pattern`, `similar_incident_unresolved`)

### What the plane IS NOT

These boundaries are non-negotiable and codified as test invariants
in Phase 1+:

- **Not in the synchronous `/predict` path.** No retrieval call
  blocks model inference. Latency budget for serving is preserved.
- **Not authoritative.** A query that returns nothing must never
  block a deploy, retrain, or rollout — only the system of record
  can. The plane provides *context*, not *gates*.
- **Not a policy mutator.** It cannot relax AUTO/CONSULT/STOP modes.
  It can only ESCALATE prudence — same rule as ADR-010 dynamic
  signals (line 52). Memory hits never demote a STOP to CONSULT.
- **Not a raw-log indexer.** Indexing every Pod log line is
  out of scope — too noisy, too expensive, too many false matches.
  Inputs are STRUCTURED evidence: audit entries, JSON reports,
  postmortem markdown, security findings. Phase 2 enforces this.
- **Not mandatory.** Adopters opt in via the `companions/` directory
  pattern (see ADR-003). A scaffolded service runs production-clean
  without ever calling memory APIs.

### Memory unit canonical schema

```json
{
  "id": "uuid",
  "tenant_key": "org/repo",
  "service": "fraud_detector",
  "environment": "staging",
  "memory_type": "incident|decision|drift|deploy|retrain|security|postmortem",
  "summary": "<= 280 chars, deterministic when LLM summarizer absent>",
  "severity": "low|medium|high|critical",
  "timestamp": "ISO-8601 UTC",
  "source_kind": "gha|audit|drift|performance|human",
  "source_ref": "run_id | issue_id | artifact path",
  "tags": ["k8s", "hpa", "incident"],
  "evidence_uri": "gs://bucket/path  or  s3://bucket/path",
  "resolution": "free-form, optional",
  "outcome": "resolved|mitigated|wontfix|investigating",
  "dedup_hash": "sha256(canonical_payload)",
  "embedding": "vector(<dim>)",
  "sensitivity": "public|internal|restricted",
  "retention_class": "30d|90d|1y|forever"
}
```

`MemoryUnit` is `frozen=True`. Construction validates `dedup_hash`,
non-empty `summary`, normalized `severity`, and that `sensitivity`
≥ the minimum required by `evidence_uri` bucket ACL.

### Phase plan (high-level — each phase becomes its own PR)

| Phase | Title | Ships | Acceptance |
|-------|-------|-------|------------|
| 0 | Scope + non-goals + threat model | this ADR | ADR approved |
| 1 | Canonical contracts + redaction | `common_utils/memory_types.py`, `memory_redaction.py`, unit tests | invariants green; serialization stable |
| 2 | Ingestion pipeline | `scripts/memory_ingest.py`, `scripts/memory_backfill.py`, hooks in `audit_record.py` + `deploy-common.yml` + `drift-detection.yml` | backfill over `ops/audit.jsonl`; zero secrets persisted |
| 3 | Storage + retrieval API | Postgres + pgvector schema, FastAPI service, `companions/operational-memory/` | p95 retrieval < 250ms; precision@5 measured |
| 4 | Agent / workflow integration | hooks in `risk_context.py` and skills (`rollback`, `model-retrain`, `release-checklist`); new risk signals | step-summary "memory evidence" sections; queries audited |
| 5 | Shadow → advisory → guarded-gate → enforced | grafana dashboard, prom alerts, integration tests | 30 days in shadow with measured precision@5 |
| 6 | Hardening enterprise | Terraform under `companions/operational-memory/infra/`; tenancy / RLS / retention / DR | restore test passes; policy tests green |

Phases 1–6 only proceed if their predecessor's acceptance criteria
are met AND the previous phase's ADR addendum is merged. We can
pause at any phase boundary without leaving the template in a half-
shipped state — that's the whole point of the phasing.

## Threat model (Phase 0 ratification)

The plane processes potentially sensitive operational evidence.
The threat model below MUST hold from Phase 1 onward.

### Assets

- Memory units (summaries, severities, resolutions)
- Evidence URIs and the raw evidence behind them (logs, configs,
  payloads, postmortem drafts)
- Embeddings (semantic-search vectors derived from summaries)
- Query logs (who asked the plane what, and when)

### Adversaries (in priority order)

1. **A leaked CI token holder** who can call the retrieval API and
   exfiltrate cross-environment incident history.
2. **A misconfigured agent** that captures secret values into a
   summary or evidence file because redaction missed them.
3. **A malicious contributor** who tries to ingest crafted
   evidence to poison future agent decisions ("similar incident
   resolved by disabling the security scan").
4. **A future model** with a longer context window than today's,
   that can correlate across more memory units than the current
   per-query top-k limit anticipates.

### Mitigations (codified in Phase 1+)

- **D-17 redaction at ingest**: every `MemoryUnit.summary` and every
  evidence file passes through `memory_redaction.py` (gitleaks
  patterns + custom regex for `os.environ` access + `kubectl get
  secret` output). Redaction misses are tested against a curated
  `tests/fixtures/redaction_corpus/` of historical leaks.
- **Sensitivity tier gates retrieval**: `restricted` units never
  return outside the calling environment's tenancy. Cross-env
  queries (`recall incidents from prod while running in dev`) are
  rejected at the API layer with `403`.
- **Append-only**: memory units are immutable post-ingest. Updates
  go through `memory_feedback` (separate table) — never mutate the
  original. This prevents an attacker from rewriting history.
- **Contributor evidence is opt-in**: `source_kind=human` requires
  explicit approver sign-off and is flagged in retrieval results
  with `human_authored: true`. Agents must lower confidence for
  human-authored memories with no corroborating machine evidence.
- **Tenancy isolation**: Phase 6 enforces row-level security on
  `tenant_key`. Until Phase 6, single-tenant deployment only;
  the `tenant_key` field is reserved for future use but the plane
  refuses to install in multi-tenant mode.
- **Query audit**: every retrieval call writes an `AuditEntry` with
  `agent`, `operation=memory-recall`, `inputs={query, filters}`,
  `outputs={hit_ids, scores}`. This makes shadow-mode evaluation
  possible AND deters exfiltration.

### Out-of-scope for this ADR (deferred)

- Cross-org tenancy (Phase 6+; revisit if a real adopter needs it)
- Vector embedding rotation when the underlying model changes
  (handled at Phase 5 boundary)
- Privacy-preserving retrieval (homomorphic encryption,
  differential privacy on embeddings) — adds complexity
  disproportionate to the scale this plane targets

## Consequences

### Positive

- Closes the cross-surface evidence-correlation gap that today
  forces humans to manually grep across 5 surfaces.
- Provides a NEW dynamic risk signal (`repeat_failure_pattern`)
  that ADR-010's escalation table can consume, strengthening the
  AUTO→CONSULT→STOP protocol.
- Demonstrates the `companions/` pattern (ADR-003) at production
  scale — useful for any future opt-in capability.
- Auditability: every memory query is itself audited, so retrieval
  can never become a covert side channel.

### Negative / cost

- **Operational complexity**: one new service (FastAPI), one new
  database (Postgres + pgvector), one ingestion worker.
  Justification: acceptable because it ships as opt-in companion;
  the core template runs zero memory infrastructure.
- **Calibration cost**: Phase 5's shadow-mode requires 30 days of
  baseline data before we can measure precision@5 honestly. Until
  then, signals from the plane are advisory only.
- **Schema evolution risk**: `MemoryUnit` is a contract. Breaking
  changes require migration scripts and a major version bump.
  Phase 1 gates this with a contract test that fails on
  unannotated field renames.

### Neutral

- The plane consumes existing evidence; no new collection points
  are required at the source. This means adopters who already use
  the audit trail get memory ingest for free at Phase 2.

## Engineering calibration check

Per `AGENTS.md` engineering-calibration principle: *"the solution
must match the scale of the problem."*

This plane is justified ONLY because:

1. The template targets multi-service operations (3+ services per
   adopter) where cross-service incident recall has real value.
2. The audit trail (`ops/audit.jsonl`) ALREADY exists — we are
   deriving structure from data we collect anyway, not collecting
   new data.
3. The `companions/` opt-in pattern means adopters who don't want
   the complexity simply don't enable it. Core template invariants
   stay untouched.

If those three conditions degrade — for example, the template
gets used predominantly for single-service adopters — this ADR
should be revisited and possibly deprecated.

## Acceptance criteria (Phase 0 only)

- [x] ADR approved with explicit scope + non-goals
- [x] Threat model ratified (assets, adversaries, mitigations)
- [x] Phase plan published with measurable per-phase acceptance
      criteria
- [ ] Phase 1 PR opens within 30 days (ADR-018 §Phase 1)
- [ ] If Phase 1 acceptance fails, this ADR moves to `Status:
      Withdrawn` rather than dragging across multiple sprints

## Revisit triggers

- Phase 1 implementation reveals a contract mismatch with
  `risk_context.py` that requires changing ADR-010 → re-open this
  ADR.
- An adopter requests cross-org tenancy → re-evaluate Phase 6
  scope, possibly extract the plane to its own repo per ADR-003.
- A retrieval call ever lands inside the synchronous `/predict`
  path → STOP-class incident; this ADR is the policy that says no.
