# ADR-047 — Migrating the template from MLflow 2.18 to 3.x

- **Status**: Proposed
- **Date**: 2026-09-08
- **Deciders**: template maintainer
- **Related**: ADR-033 (local-first stack profile), `.security-baselines/trivy-fs.trivyignore`,
  ADR-046 (the baseline-with-expiry idiom this follows)

## Context

Switching on the Python dependency scan surfaced **24 fixable CRITICAL/HIGH
findings** that had been present and unexamined. **Twenty of them, including
all seven CRITICAL, are MLflow**, pinned at `~= 2.18.0`; every fix is in the
3.x line, outside the compatible-release range.

They were accepted in `.security-baselines/trivy-fs.trivyignore` with a
**2026-12-08 expiry** and one review question: *has the MLflow 3.x migration
ADR been written?* This is that document.

## What was measured

Against **MLflow 3.16.0**, executed rather than read from release notes.

### The API surface is small and it survives

The template touches MLflow in exactly two files —
`training/train.py` and `training/promote_to_mlflow.py` — through eleven
calls. All eleven were exercised against a real tracking store:

| call | 3.16 |
| --- | --- |
| `set_experiment`, `start_run`, `set_tracking_uri` | works |
| `log_params`, `log_metrics`, `log_metric` | works |
| `log_artifact`, `log_artifact(artifact_path=…)` | works |
| `set_tag`, `set_tags` | works |
| `sklearn.log_model(artifact_path=…, registered_model_name=…)` | works (`artifact_path` deprecated in favour of `name`, still accepted) |
| `register_model` | works |
| `MlflowClient.set_registered_model_alias` | works |

### The model round-trip is intact

3.x changed the sklearn flavour's default serialization to `skops`, so
`log_model` succeeding proves nothing on its own. Logging then reloading a
fitted `Pipeline` gives **identical predictions** through all three paths the
template and its operators use:

- `mlflow.sklearn.load_model("runs:/…/model")`
- `mlflow.pyfunc.load_model(…)`
- `mlflow.sklearn.load_model("models:/<name>@champion")` — the alias mechanism
  `promote_to_mlflow.py` depends on

### The template's own logging code runs

`Trainer._log_to_mlflow` — the shipped method, not a reimplementation of it —
completed against 3.16, recording one run with `metrics.roc_auc`, `metrics.f1`,
`params.n_estimators`, `params.max_depth`, `tags.git_commit`,
`tags.environment`, and registering the model.

### MLflow 3.16 carries no fixable CRITICAL/HIGH findings

A resolved environment scanned at the gate's own threshold: **zero**. The
migration removes twenty of the twenty-four baselined entries and all seven
CRITICAL ones.

## The blocker, and it is not an API

**MLflow 3.x refuses the filesystem tracking backend by default:**

```text
MlflowException: The filesystem tracking backend (e.g., './mlruns') is in
maintenance mode and will not receive further updates. Please migrate to a
database backend (e.g., 'sqlite:///mlflow.db') …
```

This template defaults to a file store in **five** places, including the code
default and the `local` profile that ADR-033 defines as the no-cloud path and
that an adopter runs first:

- `src/{service}/config.py` — `tracking_uri: str = "file:./mlruns"`
- `configs/config.yaml`
- `configs/profiles/local.yaml`
- `config/adopter_context.example.yaml`
- `.env.example`

So the migration is not a version bump. It changes the default local
experience, and anyone with existing runs needs `mlflow migrate-filestore`.
`staging` and `prod` profiles already point at an MLflow server and are
unaffected.

## What was NOT verified

Stated because the gap is the interesting part:

- **The full training pipeline end to end.** Four separate configuration
  guards stand between the CLI and the MLflow call — the EDA gate (D-16), the
  `split.acknowledge_iid` requirement, and the placeholder schema disagreeing
  with the example config. Every one is the template working as designed, and
  none is an MLflow concern, but it means the 700-line path was not run whole.
- **`promote_to_mlflow.py` end to end**, for the same reason.
- **Behaviour against a real MLflow server.** Everything above used a local
  SQLite backend, not the `http://mlflow…:5000` the staging and prod profiles
  point at.

## Decision

**Proposed, not taken.** The evidence says the migration is safe for this
template's usage and removes every CRITICAL finding it carries. What it does
not settle is the file-store question, which belongs to ADR-033's local-first
contract rather than to a dependency bump — and this is a *template*, so
pinning `~= 3.16` decides the MLflow major version for every adopter.

If it proceeds, the change is:

1. `mlflow ~= 2.18.0` → `~= 3.16.0` in `templates/service/requirements.txt`;
2. the five file-store defaults → `sqlite:///mlflow.db`;
3. a `MIGRATION.md` entry pointing existing adopters at `mlflow migrate-filestore`;
4. removal of the twenty MLflow entries from `.security-baselines/trivy-fs.trivyignore`;
5. the full pipeline exercised once, with the four configuration guards
   satisfied, before any of it merges.

The 2026-12-08 expiry stays as the forcing function. If that date arrives with
no decision, the gate fails — which is the point of having put a date on it.

## Alternatives considered

**Bump MLflow and keep the file store via `MLFLOW_ALLOW_FILE_STORE=true`.**
Cheapest, and it preserves the local experience exactly. Rejected as the
default: it opts out of a deprecation the upstream project has announced, so
the template would be teaching adopters to postpone a migration that is coming
anyway. Reasonable as a documented escape hatch for an adopter mid-migration.

**Widen the pin to `>=2.18,<4` and let adopters choose.** Superficially
respects that this is a template. Rejected: it violates the repo's own
compatible-release pinning convention, and it moves a decision with a known
breaking change onto people who have not measured it — the template would be
shipping the ambiguity rather than resolving it.

**Do nothing and renew the expiry.** Rejected. The findings are real, the fix
exists, and renewing a date without a decision is the habit
`check_baselines_expiry.py` exists to prevent.

## Consequences

- Twenty of twenty-four baselined findings disappear, and every CRITICAL one.
- The local tracking backend becomes SQLite; `mlruns/` gives way to a database
  file, with a one-time migration for existing users.
- MLflow remains a training and tracking dependency: `app/` does not import it,
  so none of these findings ever touched the inference path. That is why this
  is a scheduled migration and not an incident.
