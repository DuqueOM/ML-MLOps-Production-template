# Reports v1

**Authority**: `docs/decisions/ADR-023-agentic-portability-and-context.md` §F6
**Sources**:

- `templates/config/report_schema.json` — JSON Schema (draft 2020-12)
- `templates/service/common_utils/reports.py` — typed dataclasses + serializer
- `scripts/generate_report.py` — read-only CLI (`validate`, `example`)

---

## Why a typed report contract

Before F6 each workflow generated its own ad-hoc Markdown summary or
GitHub Issue body. Dashboards parsed them with brittle regexes; CI
gates re-implemented the same field checks; a humble "is this a
release report or an incident report" question required reading the
title, not a typed field. The cost compounds with every new
dashboard.

F6 freezes a single shape per report type. The shape is enforced at
**three** layers (JSON Schema, runtime dataclass, contract test) so
no producer can drift silently. Reports are immutable: a new fact
is a new report file, never a mutation of an old one.

## Four canonical types

| Type | Producer workflow | Mode | Required environment |
| ------ | ------------------- | ------ | ---------------------- |
| `release` | `/release` | CONSULT (staging) / STOP (prod) | yes |
| `drift` | `/drift-check`, `drift-detection` | AUTO | optional |
| `training` | `/retrain`, `model-retrain` skill | AUTO | optional |
| `incident` | `/incident` | CONSULT during, AUTO post-mortem | yes |

The four-type cap is intentional. Adding a fifth type requires:

1. An ADR documenting why an existing type is insufficient.
2. A new entry in the `report_type` enum of the schema.
3. A new payload class + dataclass in `common_utils/reports.py`.
4. A new example in `scripts/generate_report.py`.
5. Test cases in `test_reports_contract.py`.

The friction is deliberate — `report_type` is part of the public
contract.

## Shared envelope

Every report carries the same outer keys:

| Key | Required | Notes |
| ----- | ---------- | ------- |
| `schema_version` | yes | Currently `1`; bump = ADR. |
| `report_type` | yes | Enum from the four canonical types. |
| `report_id` | yes | Stable id. Convention: `<type>-<service>-<UTCstamp>[-suffix]`. |
| `service` | yes | Service slug (lowercase, `[a-z][a-z0-9_-]{1,63}`). |
| `generated_at` | yes | UTC ISO8601 (`Z` or `+00:00`). |
| `generated_by` | yes | `Agent-<Name>` or `human:<user>`. |
| `mode` | yes | `AUTO` / `CONSULT` / `STOP` (mirrors AgentMode). |
| `environment` | sometimes | Required for `release` + `incident`. |
| `approver` | sometimes | Required when `mode` is `CONSULT` or `STOP`. |
| `links` | optional | List of `{label, url}` for navigability. |
| `payload` | yes | Type-specific body, see schema. |

## Storage convention

Reports live under `ops/reports/<type>/<report_id>.json`:

```text
ops/
└── reports/
    ├── release/
    │   └── release-fraud_detector-20260503T180000-0.7.0.json
    ├── drift/
    │   └── drift-fraud_detector-20260503T013000.json
    ├── training/
    │   └── training-fraud_detector-20260503T150000-mlflow_a.json
    └── incident/
        └── incident-fraud_detector-20260503T154500-INC-20260503001.json
```

The directory is template-tracked (an empty `.gitkeep` per type)
so workflows don't have to ensure the path exists at runtime.

Per-adopter retention policy is out of scope for v1 — the template
expects a CronJob cleanup or S3/GCS lifecycle rule running outside
this layer.

## Three commands

```bash
make report-validate FILE=ops/reports/release/<id>.json   # exit 0/1
make report-example TYPE=release                          # stdout
python3 scripts/generate_report.py validate <path>        # same as make
python3 scripts/generate_report.py example <type>         # same as make
```

The CLI deliberately does **not** ship a `generate` mode that takes
loose values from the command line. Real reports must be produced
by the workflow that owns the data (release-checklist, drift
detection, retrain, incident response). A free-form `generate`
would invite an agent to invent fields it does not know — exactly
the anti-pattern this layer prevents.

## Producer integration

The four producer workflows construct reports in code via the
typed builders:

```python
from common_utils.agent_context import AgentMode, Environment
from common_utils.reports import (
    ReleasePayload, build_release_report,
)

report = build_release_report(
    service="fraud_detector",
    generated_by="Agent-K8sBuilder",
    mode=AgentMode.CONSULT,
    environment=Environment.STAGING,
    approver="platform_engineer",
    payload=ReleasePayload(...),
)
report.write("ops/reports/release/" + report.report_id + ".json")
```

`ReportEnvelope.write()` creates the parent dir and writes the JSON.
It does not log to stdout, does not append to the audit log, and does
not call out to MCPs. Audit-log entries (per AGENTS.md) remain the
responsibility of the calling workflow — the report and the audit
entry are separate artefacts with separate retention rules.

## Validation

- **At write time** — `ReportEnvelope.__post_init__` enforces the
  envelope; each `*Payload` dataclass enforces its own constraints.
- **At read time** — `validate_report_dict()` does a lightweight pass
  with no third-party deps.
- **In CI** — `scripts/generate_report.py validate` adds an optional
  `jsonschema` round-trip when the package is installed; this is the
  authoritative gate.
- **Contract test** — `test_reports_contract.py` verifies the schema
  parses, the four examples round-trip, and the negative paths
  (missing approver in CONSULT, mismatched payload type, malformed
  service slug) raise.

## Authority chain

```text
ADR-023 §F6
  └─ templates/config/report_schema.json   (canonical contract)
       └─ templates/service/common_utils/reports.py (Python implementation)
            └─ scripts/generate_report.py    (CLI wrapper)
                 └─ make report-validate / report-example
                      └─ producer workflows  (release, drift, training, incident)
```

A change at any level above `producer workflows` requires a contract
test update + (usually) an ADR amendment.
