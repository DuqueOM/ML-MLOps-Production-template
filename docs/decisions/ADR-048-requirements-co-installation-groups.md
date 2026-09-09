# ADR-048 — Requirements files that share an environment must agree on their pins

- **Status**: Accepted
- **Date**: 2026-09-09
- **Deciders**: template maintainer
- **Related**: D-05 (compatible-release pinning), ADR-035 (uv adoption / requirements as
  an export), ADR-046 (the gate-with-a-measured-scope idiom), `.github/dependabot.yml`

## Context

A generated service ships more than one requirements file, and `docs/TUTORIAL.md`
walks the adopter through installing several of them into **one** environment:
§3 installs `eda/requirements.txt`, §4 then runs `make train` in the same
virtualenv the service was installed into.

Nothing checked that they could coexist. They could not:

```text
ERROR: Cannot install scikit-learn~=1.5.0 and scikit-learn~=1.9 because these
package versions have conflicting dependencies.
ERROR: ResolutionImpossible
```

`templates/service/requirements.txt` pinned `scikit-learn ~= 1.5.0` and
`pandera ~= 0.23.0`. `templates/service/eda/requirements.txt` pinned `~= 1.9`
and `~= 0.33`.

**pip never reported this**, because the tutorial issues two separate install
commands. The second silently *upgrades* what the first established. Measured
on a clean virtualenv following the documented sequence:

| package | after §2 (service) | after §3 (EDA) | declared range |
| --- | --- | --- | --- |
| scikit-learn | 1.5.2 | **1.9.0** | `~= 1.5.0` → `<1.6.0` |
| pandera | 0.23.1 | **0.33.1** | `~= 0.23.0` → `<0.24.0` |

So the adopter trains a model against scikit-learn 1.9 and serves it from an
image built with 1.5.2. That is precisely the joblib version-skew failure the
`~=` policy (D-05) exists to prevent, arriving through the one door nothing
was watching. Four more packages — numpy, pandas, pyyaml, scipy — carried
specifiers of differing *shape* (`~=1.26` vs `~=1.26.0`) that had not yet
diverged in practice but could at any release.

### How it got there

Dependabot raised the bump on both lanes. The EDA-lane PRs were **merged**
(#116 pandera, #135 scikit-learn); the service-lane PRs for the same packages
were **closed** (#132 pytest, #134 pandera). Each decision is defensible on its
own — the service pins guard model artefacts and the EDA lane does not produce
any. Together they opened a gap, and **no gate compared the two files**, so the
gap was invisible from the moment it opened.

This is the same shape as the defects this repository already hunts: a control
whose scope is narrower than the surface it guards. There were three drift
gates (`check_cicd_template_drift`, `check_common_utils_drift`,
`check_vendored_runtime_drift`) and none of them looked at dependency pins.

## Decision

**1. Requirements files are grouped by the environment they are installed into,
and a group must agree.** Within a co-installation group, a distribution
declared in more than one file must carry a **byte-identical** specifier.

Identical, not merely compatible. `~=1.26` is `>=1.26,<2.0`; `~=1.26.0` is
`>=1.26.0,<1.27.0`. They read alike and resolve differently, and the looser one
silently readmits the versions the tighter one was written to exclude — which
for numpy is the case D-05 names explicitly.

Two groups exist today:

| group | members | why they share an environment |
| --- | --- | --- |
| `generated-service` | `requirements.txt`, `eda/requirements.txt`, `eda/requirements-heavy.txt` | `docs/TUTORIAL.md` §3–§4; the heavy lane opens with `-r requirements.txt` |
| `minimal-example` | `examples/minimal/requirements.txt` | standalone demo with its own venv; never meets the service, which is why its pins may legitimately differ |

**2. Group membership is total.** `scripts/check_dependency_pin_coherence.py`
discovers files with `git ls-files` and **fails** on any tracked
`*requirements*.txt` that belongs to no group. A new file cannot join the tree
without someone deciding what it is installed alongside. Without this, adding a
file would be the cheapest way to reintroduce the defect, and the gate would go
on printing OK at its smaller size.

**3. The EDA lane declares what it uses, and nothing else.** Of the eight
packages it declared, four — scipy, scikit-learn, pandera, matplotlib — were
imported by nothing. (The only mention of pandera in `eda_pipeline.py` is the
string literal it *writes into* the generated schema file, which the service
later validates with the service's own pandera.) **Two of those four dead pins
were the ones that diverged.** matplotlib moved to the heavy lane, where
plotting actually happens.

## What was measured

Executed, not reasoned about.

- **Before:** `pip install --dry-run -r requirements.txt -r eda/requirements.txt`
  → `ResolutionImpossible`.
- **After:** the whole `generated-service` group, including the heavy lane,
  resolves cleanly.
- **After, following the tutorial's two-command sequence** in a clean venv:
  scikit-learn stays at 1.5.2 and pandera at 0.23.1 — the service's own pins
  survive step §3, which they did not before.
- **The reduced EDA lane is sufficient:** all six phases of `eda_pipeline.py`
  run to completion in a virtualenv built from `eda/requirements.txt` alone,
  emitting all five canonical artefacts.
- **The full training pipeline then runs end to end** on those artefacts —
  EDA gate, split policy, Optuna HPO, cross-validation, fit, evaluation,
  quality gates, `model.joblib`, `training_manifest.json`, and an MLflow run
  carrying metrics, params, tags and a registered model. This closes the gap
  ADR-047 recorded as *"the full training pipeline end to end — not verified"*.

### One finding that only running produced

`eda/requirements.txt` never declared **pyarrow**, and the pipeline writes
`baseline_distributions.parquet`. No `import pyarrow` appears anywhere in the
pipeline — pandas reaches for it — so a static reading of the imports cannot
see the dependency, and the lane only ever worked because the *service* set
happened to carry pyarrow. Installed standalone, as `eda/README.md` presents
it, the lane crashed in Phase 0. It is now declared, at the service's specifier,
and the coherence gate holds the two together.

The general point is worth keeping: **AST analysis proves a package is used, not
that the declared set is sufficient.** Only execution does that.

## Consequences

- One more gate (sixteen), sub-second and offline, on pre-push and in CI, with a
  scope floor in `test_gate_scope_ratchet.py` and its own negative-control suite
  in `templates/tests/governance/test_dependency_pin_coherence.py` — the gate is
  tested by reintroducing the defect, not only by passing on a clean tree.
- Dependabot may still raise a bump on one lane. It now **fails** until the
  sibling is raised with it, which turns a silent divergence into a red PR.
- The EDA lane installs less: eight declared packages become five, and the four
  removed were carrying no weight.
- **What this deliberately does not check:** transitive resolvability. Two files
  can agree on every shared *direct* pin and still conflict three levels down.
  Catching that needs a resolver and a network, which CI already spends once in
  `scripts/resolve_python_dependencies.py`. This gate is the static half — it
  catches the class that actually occurred, on every commit.

## Alternatives considered

**Make `eda/requirements.txt` a `-r ../requirements.txt` include.** Eliminates
the defect class outright rather than detecting it, which is the stronger move
in general and the one `AUDIT_R11` recommends. Rejected here because it would
drag fastapi, uvicorn and shap into an analyst's EDA environment to obtain three
shared packages — it fixes coherence by destroying the separation the EDA lane
exists to provide.

**Let the lanes diverge and document it.** Rejected: the tutorial installs them
into one environment, so "they may differ" is not a policy, it is a description
of a bug. Either the sequence changes or the pins agree.

**Compare pins repo-wide instead of by group.** Rejected: `examples/minimal` is
a standalone demo with its own virtualenv and pins `pytest ~= 9.1.1` against the
service's `~= 8.3.0`, legitimately. A gate that flagged that would be wrong, and
the pressure to silence it would land on the useful half.
