# Governance tests — about this repository, not about a generated service

These tests assert facts about **the template repository**: the wording of its
`README.md`, the shape of its own workflows, the contents of
`templates/config/*.yaml`, the presence of its release notes.

They are here rather than in `templates/service/tests/` because that directory
is the **Copier payload** — every file in it is copied into an adopter's
repository. A test about this repo, shipped to an adopter, has nothing true to
say about their service.

## What it looked like before

Measured on a freshly scaffolded service, 2026-09-07:

```text
116 failed, 567 passed, 56 skipped, 31 errors
```

**147 of 764** tests failed or errored on the adopter's very first `pytest`,
across 19 files, every one of them looking for a path like
`templates/service/Makefile` two directories above the service root. Nothing
about their service was wrong. The signal was pure noise, and noise on a first
run is worse than no tests — it teaches the adopter that red is normal.

## The boundary, and how it is held

A payload test may only anchor itself to the **service root**. Concretely, the
deepest `Path(__file__).resolve().parents[N]` a payload test may bind as its
only root is the one that lands on the service — `parents[1]` for a file
directly under the tests directory, `parents[2]` for one nested a level deeper.

`scripts/check_payload_test_scope.py` enforces exactly that, and runs in
pre-commit, `make verify` and CI.

## Adding a test here

The depth is unchanged by the move: `parents[3]` resolves to the repository
root from `templates/tests/governance/` just as it did from
`templates/service/tests/`. Moving a file is a `git mv` and nothing else.

CI runs this directory from the `Full contract suite (template context)` lane
in `.github/workflows/template-context-tests.yml`. A new file here is picked up
automatically; the directory is listed, not the files.

## What is *not* here

A test that is genuinely about a generated service stays in the payload, even
if it also has something to say about the template. Several use a
dual-perspective resolver — try the service root, fall back to the template
layout — which is the same idiom `scripts/check_doc_path_refs.py` uses. That
pattern is allowed and is not what the gate looks for.
