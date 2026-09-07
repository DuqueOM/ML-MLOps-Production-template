# ADR-035: uv adoption + Copier index publication

| | |
| --- | --- |
| **Status** | Accepted |
| **Date** | 2026-06-30 |
| **Deciders** | @DuqueOM |
| **Authority** | AGENTS.md#Engineering Calibration Principle |
| **Related** | ADR-029 (Agentic Adoption Contract), ADR-030 (Copier scaffolding), ADR-033 (Stack profiles) |

## Context

Two modernization gaps remain after Waves 1–3:

1. **B5 — `requirements.txt` + pip vs modern `uv`/`pyproject`**: The
   scaffolded service already has a `pyproject.toml`, but the Makefile
   and docs still default to `pip install -r requirements.txt`. Adopters
   from the modern Python ecosystem expect `uv sync` to work.

2. **B6 — Discoverability**: The template is not published as an
   indexable Copier template. Adopters must know the GitHub URL to
   scaffold. Publishing to a Copier index (or at minimum, documenting
   the `copier copy` invocation with the GitHub URL) improves
   discoverability.

## Decision

### W4.1 — uv support (additive, not replacing pip)

Add `uv` as a **first-class option** alongside pip:

1. The Makefile gains an `install-uv` target:

   ```makefile
   install-uv: ## Install dependencies with uv (faster, reproducible)
       uv sync
   ```

2. The `pyproject.toml` already exists and is valid. No changes needed
   to its structure — `uv` reads `pyproject.toml` natively.

3. `requirements.txt` is **retained** as a compatibility export for
   adopters who cannot install `uv` (e.g. air-gapped environments with
   only pip).

4. The `README.md` and `QUICK_START.md` mention both paths:

   ```bash
   # Option A: uv (recommended, 10× faster)
   uv sync

   # Option B: pip (compatible)
   pip install -r requirements.txt
   ```

5. No `uv.lock` is committed in the template — the lockfile is
   adopter-specific (depends on their Python version, platform, and
   optional dependencies). The `.gitignore` already excludes
   `uv.lock` if the adopter generates one.

### W4.2 — Copier index publication

The template is already structured as a valid Copier template
(`copier.yml` at repo root). Publication means:

1. Documenting the `copier copy` invocation in `README.md` and
   `QUICK_START.md`:

   ```bash
   copier copy https://github.com/DuqueOM/ML-MLOps-Production-Template.git my_service
   ```

2. Adding a "Copier template" badge to `README.md` that links to the
   Copier documentation on using indexed templates.

3. The template is **not** submitted to a central Copier index (there
   is no official Copier index registry as of 2026). Instead, the
   GitHub URL IS the index entry — `copier copy <url>` works directly.

4. Comparison badges in `README.md` §"How this compares" are updated
   to reflect the Copier-based scaffolding + local-first profile.

### W4.3 — PROGRESSION.md + ADOPTION.md updates

- `PROGRESSION.md` Stage 2 is updated to show `copier copy` instead of
  `new-service.sh`, and mentions `--profile local`.
- `ADOPTION.md` maturity matrix gains a "Scaffolding" row and a
  "Local-first profile" row.

## Invariants

- **I-035-1**: `requirements.txt` MUST remain valid and in sync with
  `pyproject.toml` dependencies. Adopters who cannot use `uv` must
  have a working pip path.
- **I-035-2**: `uv sync` MUST work on a fresh scaffolded service with
  Python 3.11+.
- **I-035-3**: The Copier invocation URL MUST be the canonical GitHub
  URL (no shortlinks, no redirects).
- **I-035-4**: No `uv.lock` in the template repo — it is
  adopter-specific.

## Scope

- **In scope**: Makefile `install-uv` target, README/QUICK_START
  updates, PROGRESSION/ADOPTION updates, comparison badges.
- **Out of scope**: migrating CI from pip to uv (CI uses pip and
  constraints.txt — changing CI is a separate decision), removing
  `requirements.txt` (retained for compatibility), submitting to a
  Copier index registry (none exists).

## Consequences

- **Positive**: adopters from the uv ecosystem feel at home.
- **Positive**: `copier copy <url>` is documented and discoverable.
- **Positive**: `requirements.txt` retained for air-gapped / pip-only
  environments.
- **Negative**: two install paths must be kept in sync
  (`pyproject.toml` and `requirements.txt`). Mitigated by I-035-1
  and the fact that `pyproject.toml` is the source of truth —
  `requirements.txt` is an export.
- **Neutral**: no Copier index registry submission — the GitHub URL
  is the index entry.

## Revisit triggers

- If a Copier index registry emerges and gains traction, submit the
  template to it.
- If `uv` becomes the de-facto standard and pip compatibility is no
  longer needed, `requirements.txt` can be removed (with a migration
  ADR).
- If CI migrates to `uv`, update the CI workflows to use `uv sync`
  instead of `pip install -r constraints.txt`.

## Alternatives considered

1. **Replace pip entirely with uv** — rejected. Breaks air-gapped
   environments and adopters without `uv`. Additive is safer.
2. **Submit to a Copier index** — rejected. No official Copier index
   registry exists as of 2026. The GitHub URL works directly with
   `copier copy`.
3. **Do nothing** — rejected. The modernization gap (B5/B6) is
   documented and adopters have asked for `uv` support.

## Related

- ADR-029 (Agentic Adoption Contract) — satisfies all 5 conditions.
- ADR-030 (Copier scaffolding) — the Copier URL IS the index entry.
- ADR-033 (Stack profiles) — `copier copy --data profile=local` is
  documented in the README.
