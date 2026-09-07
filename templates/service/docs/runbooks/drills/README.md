# Operational drills

> Reproducible operational simulations that exercise a production code
> path against deterministic synthetic inputs and produce auditable
> evidence on disk. Drills are how the template proves — every quarter,
> after every refactor — that the gates still gate.

## Why drills (and not "just tests")

A unit test asserts that a function returns the right value. A drill
asserts that the **operational flow** still produces the right
**verdict** when something realistic goes wrong. The two failure modes
look identical to the function under test but very different to the
people on call:

| | unit test | drill |
| -- | ----------- | ------- |
| **scope** | one function, one input | end-to-end code path |
| **input** | toy fixtures | deterministic synthetic data that mirrors a real failure |
| **output** | pass/fail | pass/fail **+ human-readable evidence on disk** |
| **cadence** | every PR | every release + quarterly |
| **audience** | developer | on-call + auditor |

A drill that has been running clean for three quarters and then breaks
is one of the strongest signals an MLOps system can produce: something
upstream changed in a way that bypasses a documented gate.

## What ships

The template ships TWO drills (PR-C3, ADR-015 acceptance #10):

- **`drift`** — `scripts/drills/run_drift_drill.py`
  Injects a +3σ shift on `feature_a` against a synthetic baseline,
  runs the production `detect_drift(--eda-baseline …)` path, asserts
  PSI on the shifted feature exceeds the alert threshold AND the two
  untouched features stay below warning. **Expected verdict**:
  `alert_on_feature_a`.

- **`deploy_degraded`** — `scripts/drills/run_deploy_degraded_drill.py`
  Trains a logistic-regression champion on a separable binary task,
  trains a degraded challenger on the SAME features but with shuffled
  labels (AUC ≈ 0.50), runs the production
  `champion_challenger.compare_models` decision engine, asserts the
  decision is `block`. **Expected verdict**: `block`.

## Where evidence lives

```text
docs/runbooks/drills/
    <drill_name>/
        <run_id>/                        # <UTC compact>-<short uuid>
            evidence.md                  # human-readable narrative
            evidence.json                # machine-readable verdict + facts
            artifacts/
                <drill-specific outputs>
```

Both formats are written by the same `DrillEvidence` dataclass; the
markdown is what an auditor reads after an incident, the json is what
the contract test parses. Identical seed → identical evidence.json
modulo timestamps.

## Running a drill locally

```bash
# Drift drill (uses a temp dir for synthetic CSVs)
python -m scripts.drills.run_drift_drill

# Redirect evidence elsewhere
DRILL_EVIDENCE_ROOT=/tmp/my-drills python -m scripts.drills.run_drift_drill

# Deploy-degraded drill
python -m scripts.drills.run_deploy_degraded_drill
```

Exit codes are stable:

- `0` — drill PASSED (verdict matches expectation)
- `1` — drill FAILED (verdict diverged — investigate immediately)
- `2` — internal error (bootstrap, missing dependency)

## Cadence

| Trigger | Drills to run |
| --------- | --------------- |
| Every PR (scaffold smoke) | both, via `test_drills_reproducible.py` |
| Every release | both |
| After any change to `monitoring/drift_detection.py` | `drift` |
| After any change to `evaluation/champion_challenger.py` | `deploy_degraded` |
| Quarterly recurring | both, evidence committed under `docs/runbooks/drills/` |

## Adding a new drill

1. Add `scripts/drills/run_<name>_drill.py` following the two
   shipped drills as templates. The script MUST:
   - Build deterministic synthetic inputs (named seeds in module-level
     constants).
   - Exercise the actual production module by importing it from
     `src/<service>/...` (no copy-paste of business logic).
   - Compare the verdict against an `EXPECTED_VERDICT` constant.
   - Emit a `DrillEvidence` via `_drill_common.write_evidence()`.
   - Use exit codes `0` / `1` / `2` per the contract above.

2. Add a test case to `tests/test_drills_reproducible.py` that runs
   the drill end-to-end against a tmp_path and asserts the evidence
   shape + verdict.

3. Add a row to the cadence table above.

## What this README explicitly does NOT cover

- **Live-cluster drills** (e.g. actually deploying a degraded image to
  a kind cluster and asserting Argo Rollouts aborts). Live-cluster
  drills belong in the golden-path workflow (PR-A5) and run on a
  schedule, not in the per-PR smoke chain. The drills here are the
  **logic** verification; the golden-path is the **infrastructure**
  verification. Two separate gates.
- **Chaos engineering** (random pod kills, network partitions). Out
  of scope for the template — owned by platform team if/when it exists.
- **Performance drills** (latency, throughput regressions). See the
  `/load-test` workflow + `locustfile.py`; that's a different artifact
  with a different cadence.
