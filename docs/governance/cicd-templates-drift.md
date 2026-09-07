# CI/CD Templates Drift Gate

**Status**: Active enforcement (v0.16.1+); scan scope widened to all of `templates/` on 2026-09-04
**Enforcement**: `scripts/check_cicd_template_drift.py` + `cicd-template-drift` job in `.github/workflows/validate-templates.yml`
**Related**: ADR-025 (`common_utils` distribution), ADR-026 (branch protection)

## What this gate enforces

For every GitHub Action `X` that appears in BOTH `.github/workflows/`
(the runtime workflows of the template repo itself) and anywhere under
`templates/` (scaffolder inputs copied verbatim into adopter services,
plus copy-me artifacts such as `templates/governance/`), the set of
versions used under `templates/` must be a subset of the set of versions
used in `.github/workflows/`.

If templates use any version not present in runtime, the gate fails the
PR with a structured diff.

### Scan scope (widened 2026-09-04)

The gate originally scanned `templates/service/.github/workflows/` alone,
on the assumption that the scaffolder's workflow directory was the only
place shipping action references to adopters. It was not.
`templates/governance/promote-with-approval.yml` is copied into the
adopter's own `.github/workflows/` by hand (see
`templates/governance/README.md`) and carried a floating
`actions/setup-python@v5` — two majors behind runtime, unpinned against
the SHA-pinning policy the rest of the repo follows — for as long as this
gate had existed, precisely because it sat outside the scan scope.

A gate whose scope is narrower than the surface it is trusted to cover
reports green while the contract rots. The scope is now the whole
`templates/` tree.

Widening costs nothing in false positives. The comparison is an
intersection over action names, so template-only actions remain ignored
exactly as before (see "What this gate does NOT enforce").

## Why this gate exists

Dependabot's `github-actions` ecosystem scans `.github/workflows/`
relative to the configured `directory:` in `.github/dependabot.yml`. It
does not — and cannot trivially — scan YAML under `templates/` because
those files are scaffolder inputs and copy-me artifacts, not executable
workflows of the template repo.

The blast radius is concrete:

```text
1. Dependabot opens PR: actions/upload-artifact v4 -> v7 in .github/workflows/
2. PR is merged. Runtime workflows are now on v7.
3. templates/ still references v4 (Dependabot never saw those files).
4. An adopter runs `make new-service` today.
5. The new service is scaffolded with v4 references.
6. The adopter's own Dependabot opens the SAME bumps the template
   already merged, multiplying maintenance cost across every fork.
```

Without this gate, the divergence is invisible until an adopter notices
their scaffolded service has stale CI references — by which point the
contract has already shipped.

## What this gate does NOT enforce

- Action versions under `templates/` that are NOT also used in
  `.github/workflows/`. Some template-only actions exist by design
  (`google-github-actions/auth`, `aws-actions/configure-aws-credentials`,
  `infracost/actions/setup`) because the template repo doesn't deploy
  to a real cloud but adopters do. Those have no parallel reference to
  compare against.
- Whether a shared action SHOULD be used in both places. That's an
  architecture decision, not a drift question.
- SHA-pinned versus tag-pinned references *directly*. What the subset
  rule does catch, as a side effect, is a template floating on a tag
  (`@v4`) while runtime has moved to a SHA: the tag is a version runtime
  does not use, so the gate fails. That is how the floating
  `actions/setup-python@v5` and `actions/checkout@v4` in
  `templates/governance/promote-with-approval.yml` surfaced the moment
  the scope was widened. A dedicated `--require-sha` mode remains
  separate hardening.

## How drift is fixed

When the gate fails, it prints the action, the runtime versions, and
the template versions. The fix is mechanical: bump the offending
references under `templates/` to a version already used in
`.github/workflows/`. The script's error message includes the exact
versions to remove.

For intentional divergence (e.g., a template needs an older version
for backward compat with a specific runner), add an exception inside
`scripts/check_cicd_template_drift.py` with an inline comment linking
to the ADR or governance doc that justifies the deviation.

Note that the fix is always to move the *template* forward, never to
relax the gate. Runtime is the source of truth because Dependabot
updates it; a template version that runtime does not use is, by
construction, a version nobody is testing.

## Required check posture

This gate runs on every PR but is **not** in the required-status-checks
list codified by ADR-026 (`docs/governance/branch-protection.md`).
That list is intentionally minimal — six always-on checks that protect
the core invariants. Adding `cicd-template-drift` to required would
require:

1. PR amending `docs/governance/branch-protection.md` to extend the
   required-checks list to seven entries.
2. Update to ADR-026 §Revisit triggers documenting why the seventh
   slot is justified.
3. Re-running `make setup-github` to push the updated ruleset.

Until that consensus exists, the gate enforces via merge friction (a
red check is visible to reviewers) rather than via hard server-side
block. This matches the posture of `common-utils-drift` (ADR-025).

## Why a script and not a yaml-only check

The check could in principle be expressed inline as a `grep`-and-diff
shell snippet. The script form was chosen for three reasons:

1. **Clear failure messages.** The drift report prints the exact
   action, the version sets on each side, and the template-only
   versions to remove. A `grep` pipe would print line numbers without
   semantic context.
2. **Future extensibility.** When SHA-pinning is added (separate
   governance work), the script can grow a `--require-sha` mode
   without changing the workflow yaml.
3. **Reusability.** Adopters can add the same check to their own forks
   if they fork-and-modify `templates/`, by reusing the script.

## Operational cost

Empty repo state (no shared actions): `O(0)` work — the script returns
0 immediately. Typical state (9 shared actions across the `templates/`
tree + the runtime workflows): tens of milliseconds on a CI runner,
dominated by Python startup. Widening the scan from one directory to the
whole `templates/` tree added a few dozen files to the walk and did not
move the measurement. Negligible in CI budget terms.

## Revisit triggers

This gate becomes obsolete (and removable) when Dependabot grows
support for scanning arbitrary template directories under
`github-actions` ecosystem, OR when the template workflows are replaced
by a generation step that derives them from `.github/workflows/` at
scaffold time. Neither is on the immediate roadmap; the gate is the
correct calibration today.
