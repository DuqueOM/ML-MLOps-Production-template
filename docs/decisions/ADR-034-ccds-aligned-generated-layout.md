# ADR-034: CCDS-aligned generated layout view

| | |
| --- | --- |
| **Status** | Accepted |
| **Date** | 2026-06-30 |
| **Deciders** | @DuqueOM |
| **Authority** | AGENTS.md#Documentation Invariants |
| **Related** | ADR-029 (Agentic Adoption Contract), ADR-030 (Copier scaffolding), ADR-033 (Stack profiles) |

## Context

The Cookiecutter Data Science (CCDS) template popularized a directory
layout that most data-science practitioners recognize instantly:

```text
data/           # raw, interim, processed, external
notebooks/      # exploratory Jupyter notebooks
models/         # trained model artifacts
references/     # data dictionaries, schemas, papers
src/            # source code
```

Our template uses a production-oriented layout optimized for K8s
deployment, DVC pipelines, and the agentic spine:

```text
data/           # raw, processed, reference, production, validated
eda/            # structured EDA pipeline + notebooks
models/         # trained artifacts (DVC-tracked)
reports/        # JSON/HTML metrics, drift, champion-challenger
src/<service>/  # training, serving, monitoring source
app/            # FastAPI application
k8s/            # Kubernetes manifests
infra/          # Terraform
```

Adopters from a CCDS background report that the production layout is
not immediately recognizable. The gap is **recognizability**, not
functionality — our layout is correct for production, but it lacks a
mapping that helps practitioners orient themselves on day 1.

## Decision

Generate a **CCDS alignment view** — a documentation artifact, not a
directory restructure — that maps our production layout to the CCDS
vocabulary. The mapping is emitted at scaffold time in
`docs/CCDS_MAPPING.md` and linked from the service `README.md`.

### Mapping table

| CCDS directory | Template location | Notes |
| ---------------- | ------------------- | ------- |
| `data/raw/` | `data/raw/` | Direct match — DVC-versioned inputs |
| `data/interim/` | `data/validated/` | Pandera-validated frames (cache) |
| `data/processed/` | `data/processed/` | Direct match — featurised output |
| `data/external/` | `data/reference/` | Frozen distributions, SHAP background |
| `notebooks/` | `eda/notebooks/` | Structured EDA companion notebooks |
| `models/` | `models/` | Direct match — DVC-tracked artifacts |
| `references/` | `docs/` + `eda/artifacts/` | Data dictionaries, schemas, EDA summaries |
| `src/` | `src/<service>/` | Direct match — service source code |

### What is NOT changing

- **No directory rename or move** — the production layout stays as-is.
  The CCDS mapping is a **read-only view** (documentation), not a
  structural change.
- **No symlink farm** — symlinks create maintenance burden and
  cross-platform issues (Windows). The mapping is a Markdown table.
- **No CI impact** — the mapping does not affect `dvc.yaml` paths,
  Makefile targets, or K8s manifests.

### What IS changing

1. `docs/CCDS_MAPPING.md` is generated at scaffold time (Copier
   template file).
2. The service `README.md` gains a "CCDS mapping" section linking to
   `docs/CCDS_MAPPING.md`.
3. `docs/TUTORIAL.md` (Wave 3 W3.2) references the mapping when
   explaining the layout.

## Invariants

- **I-034-1**: The CCDS mapping is documentation-only. No production
  path (`dvc.yaml`, `Makefile`, `k8s/`, `infra/`) may reference a
  CCDS path.
- **I-034-2**: The mapping table MUST be generated from the Copier
  template (not hand-edited per service) so `copier update` keeps it
  in sync.
- **I-034-3**: The mapping MUST NOT introduce new directories. It
  maps existing template directories to CCDS vocabulary.

## Scope

- **In scope**: `docs/CCDS_MAPPING.md` template file, `README.md`
  section, `docs/TUTORIAL.md` reference.
- **Out of scope**: directory restructure, symlink farm, CCDS-compat
  CLI wrapper, migration tooling for existing services.

## Consequences

- **Positive**: adopters from CCDS background orient in < 2 min.
- **Positive**: no runtime or CI impact — pure documentation.
- **Negative**: the mapping can drift if directories are renamed
  without updating the template. Mitigated by I-034-2 (template-
  generated) and the vendored runtime drift gate.
- **Neutral**: CCDS practitioners still need to learn the production
  layout for K8s/TF work. The mapping is a starting point, not a
  replacement.

## License

CCDS is MIT-licensed. No code is vendored — only the directory
vocabulary is referenced. `NOTICE` unchanged.

## Revisit triggers

- If the template adds a directory that has no CCDS equivalent (e.g.
  `monitoring/`), the mapping table is extended, not restructured.
- If a future ADR renames `data/validated/` or `data/reference/`, the
  mapping table MUST be updated in the same PR.
- If community feedback indicates the mapping is unused, it can be
  removed without deprecation (documentation-only, no runtime
  dependency).

## Alternatives considered

1. **Rename directories to CCDS names** — rejected. Breaks `dvc.yaml`,
   Makefile, K8s manifests, all contract tests, and the drift CronJob
   path contract. Cost >> benefit.
2. **Symlink farm** — rejected. Cross-platform issues, maintenance
   burden, and `dvc.yaml` does not follow symlinks reliably.
3. **Do nothing** — rejected. The recognizability gap (B3) is a
   documented adoption barrier. A documentation-only mapping is the
   minimum-cost fix.

## Related

- ADR-029 (Agentic Adoption Contract) — this change satisfies all 5
  contract conditions.
- ADR-030 (Copier scaffolding) — the mapping is a Copier template
  file, updated via `copier update`.
- ADR-033 (Stack profiles) — the mapping is profile-agnostic (same
  directories exist in all profiles).
