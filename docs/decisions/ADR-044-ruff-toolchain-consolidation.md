# ADR-044 — Consolidate black + isort + flake8 into ruff

- **Status**: Accepted
- **Date**: 2026-08-07
- **Deciders**: template maintainer
- **Supersedes**: the lint/format portion of the conventions in
  `agentic/rules/01-mlops-conventions.md` and `CLAUDE.md`
- **Related**: ADR-019 (the CI classifier keys off linter output),
  ADR-030 (Copier render root shapes the exclude list)

---

## Context

The Python lint and format layer ran three separate tools:

| Tool | Role | Pin |
| --- | --- | --- |
| `black` | formatter | 25.1.0 |
| `isort` | import ordering | 6.0.1 |
| `flake8` | style + pyflakes | 7.1.1 |

Each was a separate pre-commit repo with its own `args`, its own `files`
pattern, and its own copy of the same eight-line `exclude` regex. That
block was duplicated **six times**: three tools × two pre-commit configs
(the template's own and the scaffolded service's). Their settings were
additionally mirrored in `[tool.black]` and `[tool.isort]` sections of two
`pyproject.toml` files.

Consolidation was proposed on the grounds that the setup was "old
architecture" and slow.

### The speed argument did not survive measurement

Before assuming, the suite was timed:

```console
$ pre-commit run --all-files      # cold, installing envs
TOTAL WALL: 28.07 s

$ pre-commit run --all-files      # warm
TOTAL WALL: 2.62 s
```

`--all-files` is the worst case; a real commit touches far fewer files.
The config header's stated target is `< 5 s`, and the existing setup met
it with margin. **Speed is therefore not a reason to migrate**, and this
ADR does not claim it as one. (Ruff does turn out to be faster — 1.62 s
for the same sweep — but that was a side effect, not the case for change.)

### What actually justified the change

1. **Six copies of one exclude list.** Any scope change had to be applied
   six times or the tools would disagree about what they lint. This is the
   same class of defect as the gitleaks version drift closed in `v0.22.0`:
   one truth, several declarations, silent divergence.
2. **Coverage holes nobody had noticed.** `flake8`'s `files:` pattern was
   `^(templates/service/|examples/)`. `scripts/` and `templates/tests/`
   were type-checked by mypy and security-linted by bandit but **never
   style-linted**. Switching to ruff surfaced five real findings there,
   including a test that asserted nothing (see Consequences).

## Decision

Replace `black`, `isort`, and `flake8` with **ruff** (`ruff check` +
`ruff format`), pinned at `v0.15.15`, configured once per `pyproject.toml`
under `[tool.ruff]`.

### Rule scope is deliberately parity-only

```toml
select = ["E", "W", "F", "I"]   # pycodestyle + pyflakes + isort
ignore = ["E203"]               # conflicts with the formatter, as under black
```

This reproduces exactly what the three replaced tools enforced — nothing
more. `E203` was already in flake8's `--extend-ignore` for the same
formatter-conflict reason. `W503` has no ruff equivalent and ruff never
emits it.

### Deferred rulesets

Ruff also ships `UP` (pyupgrade), `B` (bugbear), `S` (bandit port) and
others. Enabling them was measured: **90 additional findings**.

They are deliberately **not** enabled here. Turning them on inside this
change would mix a toolchain swap with a code change — two different
reviews in one diff, where a reviewer cannot tell which line moved because
the tool changed and which moved because the rules changed. Adopting
additional rulesets is a separate decision with its own ADR.

### What ruff does NOT replace

- **mypy** — ruff performs no type checking. Retained unchanged.
- **bandit** — ruff's `S` ruleset is a partial port, and it is not enabled
  (above). Retained unchanged.

## Consequences

### The formatter output is not byte-identical to black

`ruff format` reformatted **55 of 134 files** (214 insertions, 290
deletions). This is unavoidable: the two formatters genuinely differ.

Handled with the standard playbook:

- the reflow is isolated in a single commit that changes nothing else;
- that commit is registered in `.git-blame-ignore-revs`;
- equivalence was verified by running the collectible test suite before
  and after and confirming an **identical** result (19 failed, 672 passed,
  30 skipped, 73 errors — all pre-existing local dependency gaps,
  confirmed by running the same command on `main`), plus `py_compile` on
  every reformatted file.

### Two real defects surfaced in previously unlinted directories

- `templates/tests/unit/test_risk_context.py` —
  `test_different_cache_keys_isolated` assigned `ctx1` and never read it
  (`F841`). The test is named for an isolation property it never asserted:
  it would have passed even if caching were absent entirely. Fixed by
  adding the missing `assert ctx1 is not ctx2`, not by deleting the
  variable.
- `scripts/mcp_doctor.py`, `scripts/verify_enterprise_adoption.py` —
  unused import and two over-length lines. The regex edit was verified to
  produce a byte-identical compiled pattern.

### ADR-019 classifier

The CI failure taxonomy keyed on `black.format_drift`,
`isort.import_drift`, and `flake8.lint`. `ruff.format_drift` and
`ruff.lint` were added. **The legacy keys are retained** so historical
failure logs still classify and so a service scaffolded before this
migration keeps working.

### Adopter impact

The pre-commit hook set changes: three hooks removed, two added. Under
`docs/RELEASING.md` §1.3 removing or renaming a pre-commit hook is a MAJOR
change to the adopter contract. See `MIGRATION.md` for the required
action.

## Alternatives considered

- **Keep black, use ruff only for lint.** Halves the churn (no reformat)
  but keeps two tools and two config surfaces, which is most of the
  problem. Rejected.
- **Migrate mypy to pyright at the same time.** Pyright is meaningfully
  stricter than the current `mypy --no-strict-optional` configuration, so
  it would surface a third category of findings inside an already mixed
  diff. Rejected for this change; not ruled out later.
- **Do nothing.** Defensible on speed grounds, but leaves six copies of
  the exclude list and the `scripts/` + `templates/tests/` lint hole open.
  Rejected once the hole was measured.
