# Action Plan — R6 Audit (June 2026, agentic-surface + lifecycle review)

- **Date**: 2026-06-09
- **Auditor**: Claude Code (Fable 5) session, evidence-based — every finding
  carries a file/command reference reproduced during the audit.
- **Scope**: end-to-end lifecycle coverage (DataFrame → production →
  monitoring → maintenance), agentic implementation (rules / skills /
  workflows / anti-patterns / MCPs), CI evidence lanes, doc coherence.
- **Method**: full read of AGENTS.md / README / CLAUDE.md / ADOPTION /
  manifest + execution of the repo's own validators and test suite inside
  WSL (`.venv`, Python 3.12).

## Verified green (evidence)

| Check | Result |
| --- | --- |
| `scripts/validate_agentic.py` | 107 checks OK — 15 rules, 16 skills, 12 workflows |
| `scripts/sync_agentic_adapters.py --check` | silent (no drift) |
| `scripts/validate_agentic_manifest.py --strict` | 8/8 sections OK |
| `scripts/mcp_doctor.py --mode check` / `--mode doctor` | PASS, 0 issues |
| `examples/minimal` end-to-end | train gates passed, 8/8 pytest, drift_check ALERT demo works |
| `templates/service/tests` (full, minimal venv) | 600 passed / 41 skipped / 17 failed / 52 errors — see triage below |
| Tracked binary/cache artifacts | none (`git ls-files` clean) |

## Findings

### S0 — Critical for the product's core promise

**S0-1. Claude Code never discovered the 16 skills (FIXED in this session).**
`.claude/skills/<id>.md` flat pointers are not a layout Claude Code loads;
it requires `<id>/SKILL.md` with YAML frontmatter. The 12 commands worked;
the 16 skills were invisible on the `claude` surface. Fix shipped:
`sync_agentic_adapters.py` now renders claude skills as `<id>/SKILL.md`
(frontmatter `name` + `description` extracted from the canonical skill),
`validate_agentic_manifest.py` `_adapter_path` updated, AGENTS.md parity
matrix updated. Verified live: all 16 skills became invocable in-session.
**Follow-up**: commit via PR (DCO sign-off), note as ADR-027 amendment.

**S0-2. No CI lane runs the full template-context test suite; 8 tests are
red on main today.** `policy-tests.yml` runs `tests/policy/` only;
`validate-templates.yml` runs a post-scaffold subset. Running the full
suite exposes genuinely red tests no lane catches:

- `test_dashboards_inventory.py::test_every_dashboard_file_is_listed` —
  `templates/monitoring/grafana/dashboard-dora.json` is not listed in
  `docs/observability/dashboards-inventory.md` (grep count = 0).
- `test_networkpolicy_egress_hygiene.py` (3 tests) —
  `templates/k8s/base/networkpolicy.yaml` lacks the `OVERLAY-OVERRIDE
  REQUIRED` banner the test asserts.
- `test_release_notes_follow_ons.py` — `releases/v0.16.0.md` and
  `v0.16.1.md` are missing the canonical `## Known follow-ons` section.
- `test_k8s_name_vocabulary.py::test_no_naked_service_placeholder_in_kebab_context[cronjob-drift.yaml]`
  — line ~162 `- src/{service}/monitoring/drift_detection.py` conflicts
  with the test's vocabulary rule while the file's own comment claims
  D-32 compliance; test and template disagree and must be reconciled.
**Action**: add a `template-context` CI lane that runs the full suite with
pytest markers separating scaffold-context tests (openapi snapshot,
`data/*` dirs, integration e2e) from template-context tests; fix the 8 reds.

**S0-3. Skill metadata drift: `rule-audit` still says "D-01 through D-27".**
`agentic/skills/rule-audit/SKILL.md` frontmatter description and its
invariant catalogue headings stop at D-27, while AGENTS.md and README
ship D-01..D-32. The compliance scanner itself is 5 invariants behind.
`test_anti_pattern_count_consistency.py` did not catch this — extend it
to cover skill bodies.

### S1 — High

**S1-1. Stale vendor path in AGENTS.md §MCP Integrations.** Setup section
still points to `~/.codeium/windsurf/mcp_config.json` (pre-ADR-027
Windsurf path). Claude Code reads `~/.claude.json` or repo-scoped
`.mcp.json`; surface table in `mcp_registry.yaml` is correct but the
AGENTS.md example contradicts it. Ship a per-surface example block and a
committed `.mcp.json.example` (project-scoped Claude Code MCP config) —
registry invariant I-3 (no automatic install) stays intact.

**S1-2. Test-suite isolation fragility.** 52 errors in the full run came
from `PREDICTION_LOG_ENABLED=true` leaking across tests combined with
`common_utils.prediction_logger` being unimportable when `pyarrow` is
absent; tests pass individually. Add an autouse fixture that snapshots/
restores `os.environ`, and publish a `requirements-test.txt` + one
documented command to run the full suite on the template repo.

**S1-3. Versioning narrative is confusing.** `releases/` contains
v1.0.0..v1.12.0 (Apr 2026 line) AND v0.13.0..v0.17.0 (current line);
README says "active line is v0.x; v1.0.0 reserved for L4 evidence";
CLAUDE.md says "releases/ → v1.0.0..v1.9.0". Add `docs/VERSIONING.md`
explaining the re-versioning event, mark legacy v1.x notes as historical,
fix CLAUDE.md.

**S1-4. CLAUDE.md drift.** "14 path-scoped rules" (actual: 15),
".cursor/rules → 12 glob-scoped .mdc" (actual: 15), stale releases range.
CLAUDE.md is the Claude Code context file — add it to the docs-quality
drift checks the same way `.devin/` parity is enforced.

### S2 — Medium (product depth)

**S2-1. Surface-loadability is not contract-tested.** Manifest validation
proves pointer *existence*, not that each IDE can *load* the format
(S0-1 existed precisely because of this gap). Add per-surface format
assertions: claude SKILL.md frontmatter parses, `description` non-empty
and within length limits; cursor `.mdc` frontmatter; codex layout.

**S2-2. L4 evidence remains open (acknowledged).** The v1.0.0 gate —one
real GKE + EKS rollout with VALIDATION_LOG entries, plus the four pending
runbook executions named in README §Verification (secrets-integration-e2e,
ground-truth SLA, Kyverno admission validation, secret history scan)— is
the single highest-credibility item for the niche.

**S2-3. Phase-2 of the agentic differentiators is unstarted (by design).**
ADR-018 memory plane (ingest/retrieval) and ADR-019 self-healing (patch
worker behind CONSULT) are contracts-only. The shadow-mode classifier is
wired; schedule the 14-day precision measurement so Phase 2 has its
entry evidence instead of waiting indefinitely.

**S2-4. "From DataFrame" entry point is thinner than the rest.** EDA
pipeline + leakage gate + Pandera are strong, but there is no guided
data-cleaning step (imputation/dedup/outlier policy with documented
rationale feeding `feature_catalog.yaml`). A `data-cleaning` skill +
template module would complete the claimed start of the lifecycle.

### S3 — Strategic

- Publish the niche statement prominently: supervised tabular ML services
  on K8s, 1–10 models, GCP/AWS — with explicit exits to Vertex/SageMaker.
- Agentic eval harness: `docs/agentic/red-team-log.md` exists; add
  regression evals for skills (given scenario X, agent must refuse /
  escalate per AUTO/CONSULT/STOP) runnable in CI.
- Consider an LLM-service template variant as a separate track (ADR-001
  keeps it out of scope today; the niche may demand it).

## Priority schedule

| Wave | Items | Effort |
| --- | --- | --- |
| P0 (this week) | S0-1 commit, S0-2 fixes + CI lane, S0-3 | 1–2 days |
| P1 (2–4 weeks) | S1-1..S1-4, S2-1 | 2–4 days |
| P2 (1–2 months) | S2-2 (L4 evidence), S2-3 (Phase-2 gates), S2-4 | sprint-scale |
| P3 (strategic) | S3 items | roadmap |
