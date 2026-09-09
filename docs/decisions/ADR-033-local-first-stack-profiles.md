# ADR-033 — Local-first Stack Profiles

- **Status**: Accepted
- **Date**: 2026-06-30
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none. Executes Wave 2 of
  `docs/audit/ACTION_PLAN_ADAPTABILITY.md` under the governance of
  **ADR-029** (Agentic Adoption Contract). Complements ADR-030 (Copier
  scaffolding migration) and ADR-001 (template scope boundaries).
- **Superseded by**: none
- **Related artifacts**:
  - `copier.yml` — `profile` question added (choices: `local`, `staging`,
    `prod`).
  - `templates/service/configs/profiles/` — per-profile YAML overrides.
  - `templates/service/Makefile` — `PROFILE` variable + `local-loop` target.
  - `AGENTS.md` — anti-pattern D-35.
  - `agentic/skills/stack-switch/SKILL.md` — CONSULT-mode skill.
  - `agentic/workflows/stack-switch.md` — `/stack-switch` workflow.

## 1. Context

`docs/audit/ACTION_PLAN_ADAPTABILITY.md` (gap **B2**) identifies the
second-highest-ROI adoption lever: the template assumes Kubernetes and
Terraform from day one. ZenML's "run locally, swap stacks to cloud"
gradient is the recognized entry pattern in the ML ecosystem. Adopters
who want to evaluate the template's training and serving quality gates
without provisioning a cluster face a cold-start problem:

- The Makefile's `train` target works locally, but `serve` implies
  Docker, and `deploy` implies `kubectl`.
- There is no formal concept of a "profile" — the service is either
  scaffolded (full stack) or not.
- Drift detection (`scripts/drills/run_drift_drill.py`) runs locally
  but is not wired into a "local loop" that an adopter can invoke as a
  single command.

The `examples/minimal/` directory demonstrates that the core
train→serve→drift loop works with zero cloud dependencies, but this
ergonomics has not been extended to scaffolded services.

### 1.1 Reference analysis

| Reference | Pattern | What we adopt | What we reject |
| ----------- | --------- | --------------- | ---------------- |
| ZenML | Stack profiles as swappable configuration | Profile = YAML overlay, not a separate codebase | We do not adopt ZenML's stack abstraction layer (over-engineered for 2–3 models) |
| Cookiecutter Data Science | No profile concept | — | — |
| Made With ML | Local-first notebook → production gradient | `local` profile as the default scaffold choice | We do not adopt notebook-first; code-first remains |

## 2. Decision

Introduce three stack profiles, selected at scaffold time via a Copier
question and governed by the AUTO/CONSULT/STOP protocol:

### 2.1 Profile definitions

| Profile | Scope | Mode | Cloud deps | K8s | TF | Docker |
| --------- | ------- | ------ | ------------ | ----- | ---- | -------- |
| `local` | Train + serve + drift on a laptop | AUTO | none | no | no | no |
| `staging` | Full stack targeting dev/staging cluster | CONSULT | cloud creds via IRSA/WI | yes | yes (staging) | yes |
| `prod` | Full stack targeting prod cluster | STOP | cloud creds via IRSA/WI | yes | yes (prod) | yes |

### 2.2 Profile selection at scaffold time

`copier.yml` gains a `profile` question (default: `local`). The selected
profile is written to `configs/profiles/active_profile.yaml` in the
generated service, which the Makefile and scripts read to determine
which targets are available.

### 2.3 Profile configuration overlay

Each profile is a YAML file under `configs/profiles/`:

```yaml
# configs/profiles/local.yaml
profile: local
requires:
  docker: false
  kubernetes: false
  terraform: false
  cloud_credentials: false
mlflow:
  tracking_uri: "file://./mlruns"
serving:
  host: "0.0.0.0"
  port: 8000
  workers: 1
drift:
  schedule: manual  # no CronJob
```

The `local` profile sets `mlflow.tracking_uri` to a local file path,
disables Docker/K8s/TF requirements, and makes drift detection
manual-only (no CronJob).

### 2.4 Makefile integration

The Makefile gains a `PROFILE` variable (default: `local`) and a
`local-loop` target that runs the full local cycle:

```makefile
PROFILE ?= local

local-loop: ## Run train → serve → drift in local mode (no Docker/K8s/TF)
    python src/$(SERVICE_SLUG)/training/train.py --data $(DATA_PATH)
    MODEL_PATH=$(MODEL_PATH) uvicorn app.main:app --host 0.0.0.0 --port $(PORT) &
    sleep 2 && curl -sf http://localhost:$(PORT)/health
    python scripts/drills/run_drift_drill.py
```

> **Correction (2026-09-09).** The recipe as written above could never have
> run. `train.py` opens with `from ..config import QualityGatesConfig`, and a
> file inside a package invoked as a top-level script has no package context,
> so Python raises `ImportError: attempted relative import with no known parent
> package` before the first line of logic. The shipped Makefile now uses
> `python -m src.$(SERVICE_SLUG).training.train`. The decision this ADR records
> — a `local` profile that runs the full cycle with no cloud — stands; only the
> invocation form was wrong. `tests/test_python_entrypoint_invocations.py`
> covers every surface that invokes a repository Python file, not just the
> Makefile, which is why this snippet was found.

### 2.5 Governance mapping

| Profile | Scaffold | Train | Serve | Deploy | Drift | Retrain |
| --------- | ---------- | ------- | ------- | -------- | ------- | --------- |
| `local` | AUTO | AUTO | AUTO | **blocked** | AUTO (manual) | AUTO |
| `staging` | AUTO | AUTO | AUTO | CONSULT | AUTO (CronJob) | CONSULT |
| `prod` | AUTO | AUTO | AUTO | **STOP** | AUTO (CronJob) | **STOP** |

## 3. Invariants

- **I-033-1**: The `local` profile MUST NOT accept cloud credentials,
  target a cluster, or require Docker. Violation → D-35.
- **I-033-2**: Profile selection is recorded in
  `configs/profiles/active_profile.yaml` and is the single source of
  truth for the Makefile and scripts.
- **I-033-3**: Switching profiles is a CONSULT-class operation
  (`/stack-switch` skill) because it may change the deploy target.
- **I-033-4**: The `local` profile's MLflow tracking URI MUST be a
  local file path, never a remote server.
- **I-033-5**: All profiles share the same codebase — profiles are
  configuration overlays, not separate branches or forks.

## 4. Scope

**In scope**:

- `copier.yml` `profile` question.
- `configs/profiles/{local,staging,prod}.yaml` in the template service.
- `configs/profiles/active_profile.yaml` (generated at scaffold time).
- Makefile `PROFILE` variable + `local-loop` target.
- D-35 anti-pattern + contract test.
- `stack-switch` skill + `/stack-switch` workflow.

**Out of scope**:

- Conditional file exclusion in Copier (all files are always generated;
  profiles are configuration, not file filtering).
- ZenML-style stack abstraction (over-engineered for this template's
  scale — see Engineering Calibration Principle).
- Automatic profile detection from environment (explicit selection only).

## 5. Consequences

### Positive

- Adopters can evaluate the full train→serve→drift loop in < 5 minutes
  with zero cloud dependencies, directly addressing gap B2.
- The `local` profile is the default scaffold choice, lowering the
  cold-start barrier while preserving the full production stack as an
  opt-in.
- Profile switching is governed by CONSULT mode, preventing accidental
  cloud deploys from a local profile.

### Negative

- One additional Copier question (`profile`) adds ~2 seconds to
  scaffolding. Mitigated: default is `local`, so one Enter key suffices.
- The `active_profile.yaml` file is a new source of truth that scripts
  must read. Mitigated: Makefile reads it via a one-line `sed`; scripts
  that need it already parse YAML.

### Neutral

- The `examples/minimal/` directory remains as-is — it predates profiles
  and serves a different purpose (standalone demo, not scaffolded
  service).

## 6. License & provenance (ADR-029 §1.1)

No external code is vendored. The profile concept is inspired by ZenML
(Apache-2.0, verified in ADR-030 §6) but implemented from scratch as
YAML configuration overlays. The repository remains Apache-2.0.

## 7. Alternatives considered

| Alternative | Why rejected |
| ------------- | -------------- |
| No profiles — keep full-stack-only | Gap B2 remains; adopters must provision a cluster to evaluate |
| Profiles as separate Copier templates | Triples maintenance; `copier update` cannot cross templates |
| Profiles as Git branches | Branches drift; no merge path; violates single-source principle |
| ZenML as a dependency | Adds a heavy framework for a configuration-overlay problem |
| Environment-variable-only profiles (no YAML) | Not discoverable; not version-controlled; not self-documenting |

## 8. Revisit triggers

- **Adopter telemetry shows `local` profile unused** → consider making
  `staging` the default (new ADR amendment).
- **A fourth profile is needed (e.g. `edge`)** → add a new YAML file +
  Copier choice; no structural change required.
- **Profile switching becomes frequent in practice** → consider a
  `make switch-profile PROFILE=staging` Makefile target that wraps the
  skill.

## 9. Related

- `docs/decisions/ADR-029-agentic-adoption-contract.md` — governs this wave.
- `docs/decisions/ADR-030-copier-scaffolding-migration.md` — the Copier
  migration that made profile selection at scaffold time possible.
- `docs/decisions/ADR-001-template-scope-boundaries.md` — defines what
  the template includes; profiles do not change scope, only activation.
- `docs/audit/ACTION_PLAN_ADAPTABILITY.md` — Wave 2 tracker (B2).
