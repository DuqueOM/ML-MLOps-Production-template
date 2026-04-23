# ADR-004: EDA Phase Integration into the Agentic Pipeline

## Status

Accepted

## Date

2026-04-23

## Context

The template's agentic pipeline was complete for build (scaffold → train → serve →
deploy) and operate (drift → retrain → promote) phases, but had a **silent gap
between raw data and `train.py`**: exploratory data analysis (EDA) was undocumented
and unautomated.

Consequences observed in the wild when this gap exists:
- **Data leakage shipping to production** — features with 0.98 correlation to target
  slip through because nobody ran a leakage audit
- **Pandera schemas with arbitrary ranges** — `Check.greater_than(0)` copy-pasted
  from another service instead of derived from observed distribution
- **Drift detection blind** — PSI computed against synthetic/missing baseline
  (D-15: missing `baseline_distributions.pkl`) instead of the real training distribution
- **Features added without rationale** — `features.py` full of transformations whose
  justification lived in a data scientist's head

The template positions itself as *"each phase connected, adapted, and actively contributing
to the agentic model"*. An unstructured EDA phase violates this core promise.

ADR-001 scope does **not** defer EDA. It defers: LLM, multi-tenancy, Vault, feature
store, data contracts, compliance, audit logs. EDA is core ML engineering.

## Decision

**Add EDA as a first-class agentic phase** consisting of:

1. **One rule** (`.windsurf/rules/11-data-eda.md`) — enforces structure when editing
   `eda/**` or `**/notebooks/**/*.ipynb`
2. **One skill** (`.windsurf/skills/eda-analysis/SKILL.md`) — 6-phase procedure with
   a hard gate on phase 4 (leakage detection)
3. **One workflow** (`.windsurf/workflows/eda.md`, slash command `/eda`) — triggers
   the skill, chains to `/new-service` on pass or `/incident` on leakage block
4. **One template** (`templates/eda/`) — scriptable pipeline, notebook companion,
   requirements (lightweight + heavy modes)
5. **Four anti-patterns** (D-13 through D-16) — codified invariants
6. **One new specialist agent** (Agent-EDAProfiler in Layer 2 of AGENTS.md)

The EDA phase produces 4 machine-readable artifacts consumed by other phases:

| Artifact | Consumer | Closes which loop |
|---|---|---|
| `01_dtypes_map.json` | Phase 6 schema proposal | EDA → Pandera schema |
| `02_baseline_distributions.pkl` | **Drift CronJob in production** | **EDA → drift detection** |
| `03_feature_ranking_initial.csv` | Phase 5 proposals | EDA → feature importance |
| `05_feature_proposals.yaml` | `features.py` | EDA → feature engineering |

## Rationale

### Why 6 phases, not fewer

Each phase produces a **distinct artifact consumed downstream**. Collapsing phases
would merge outputs that different downstream consumers need at different granularity:

- Phase 2's baseline (consumed by **production** drift CronJob) must be separable from
  Phase 3's ranking (consumed at **training time** only)
- Phase 4's gate output must be inspectable independently — it's the only phase that
  can HALT the pipeline

### Why phase 4 is a HARD GATE, not a warning

Data leakage is the single most common cause of "too good to be true" models that
then fail in production. A soft warning gets ignored under deadline pressure. A hard
gate (exit 1, chain to `/incident`) forces resolution:

- **Exclude**: feature is genuinely derived from target → drop it
- **Transform**: feature has overlap with target but can be used (e.g., historical
  version that doesn't leak) → document transformation
- **Justify**: with an ADR explaining why the high correlation is legitimate domain
  knowledge, not leakage

All three paths produce auditable artifacts. Dismissing the gate does not.

### Why baseline_distributions.pkl uses quantile bins

PSI (Population Stability Index) is the drift metric mandated by the template
(per D-08). PSI with uniform bins produces misleading scores for skewed features
(all mass in one bin → infinite PSI on small shifts). Quantile bins from the
reference distribution are the statistically correct choice.

The template already enforces D-08 in the drift CronJob. ADR-004 extends this: the
**baseline against which PSI is computed must also use quantile bins**, stored in
`02_baseline_distributions.pkl` during EDA phase 2.

### Why two dependency tiers (lightweight vs heavy)

`ydata-profiling` produces beautiful HTML reports but:
- ~500MB install footprint (blocks containerized CI)
- Heavy dependencies (pillow, ipywidgets, numba) that conflict with minimal
  inference environments
- Overkill for datasets <100k rows

The lightweight mode uses `pandas.describe()` + custom HTML rendering. Covers 90%
of actual usage. Heavy mode is one `pip install -r requirements-heavy.txt` away.

### Why schema_proposal.py, not auto-overwriting schemas.py

Auto-generating `schemas.py` from observed data **will** produce schemas that:
- Encode training-set quirks as hard constraints (e.g., range excludes legitimate
  outliers that appear in test)
- Miss business-rule validations that data alone can't detect (e.g., "amount must
  be non-negative even though we observed a bug that produced -1")

The engineer must **review** the proposal and selectively copy parts. The workflow
is: "EDA proposes, engineer disposes." `schemas.py` is a source-controlled contract;
it cannot be generated blindly.

## Consequences

### Positive

- The template now delivers on its "each phase connected agentically" promise across
  the full ML lifecycle
- Drift detection in production has a **real, correct baseline** (closes D-15 gap)
- Data leakage is caught at EDA time, not discovered in production via unrealistic metrics
- Pandera schemas have ranges grounded in observed data (closes D-14 gap)
- Feature engineering has documented rationale (closes D-16 gap)
- `new-service.sh` produces services with EDA infrastructure ready to run
- CI validates that the EDA template exists in every scaffolded service

### Negative

- `new-service.sh` scaffold is larger (new `eda/` directory adds ~800 lines)
- Additional dependency: `pyyaml`, `scipy`, `pandera` in EDA requirements (all already
  needed by training; no net new deps for most users)
- 6 phases add cognitive load for users who just want a quick model. Mitigations:
  - The skill defines clear success criteria per phase
  - Lightweight mode completes in seconds on small datasets
  - `eda_pipeline.py` can be run non-interactively as a one-command entry point
- Engineers who want to skip EDA and go directly to training can still do so — the
  agentic system nudges but doesn't block (except phase 4 gate on explicit leakage)

### Mitigations

- `eda_pipeline.py` is a single entry point: `python -m eda.eda_pipeline --input ... --target ...`
- The 6 phases each produce their output in seconds for typical datasets (<1M rows)
- Notebook companion offers exploration for those who prefer Jupyter
- `/eda` workflow orchestrates everything agentically — user doesn't need to remember
  the 6 phases

## Alternatives Considered

### Alternative 1: Single phase "profile" using ydata-profiling only

**Rejected.** ydata-profiling produces a report but produces no artifacts for
downstream consumers. It doesn't check leakage. It doesn't propose features. It
doesn't write a baseline for drift detection. Useful as one output among six, not
as the entire phase.

### Alternative 2: Auto-generate schemas.py and features.py

**Rejected.** Irresponsible — schema/feature code is source-controlled business
logic, not data artifacts. Generate *proposals* for human review; never overwrite.

### Alternative 3: Make EDA a manual notebook-only activity, no pipeline

**Rejected.** Breaks reproducibility. Breaks CI. Breaks the agentic promise. EDA
must be both interactive (notebook) AND reproducible (pipeline). The template
provides both.

### Alternative 4: Embed EDA artifacts into the service's `src/` directory

**Rejected.** EDA outputs are cross-cutting (feed both training AND production
drift detection). Keeping them in their own `eda/` top-level directory preserves
clear ownership and makes DVC tracking straightforward.

## Revisit When

- **Great Expectations/Soda becomes ubiquitous** and users want GE-style checks
  integrated. Currently Pandera covers single-team needs (per ADR-001).
- **LLM datasets become in-scope** (currently deferred per ADR-001). EDA for text
  corpora looks different (tokenizer stats, length distributions, PII detection)
  and warrants a separate sub-template.
- **>5 models share a feature repo** (per ADR-001 revisit trigger for Feast +
  ADR-003). At that point EDA outputs should feed the feature repo, not the service.

## References

- ADR-001: Template Scope Boundaries (EDA not in deferred list — this is core scope)
- ADR-003: Feast Integration Pattern (compatible — EDA feeds feature repo when
  Feast is adopted)
- `.windsurf/rules/11-data-eda.md`
- `.windsurf/skills/eda-analysis/SKILL.md`
- `.windsurf/workflows/eda.md`
- `templates/eda/README.md`
- Invariants: D-13, D-14, D-15, D-16 (AGENTS.md)
