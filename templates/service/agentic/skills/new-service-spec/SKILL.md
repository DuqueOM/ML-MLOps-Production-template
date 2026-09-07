---
name: new-service-spec
description: Capture the ML problem specification — label definition, fairness-sensitive attributes, false-positive/negative cost, data source — BEFORE scaffolding, so quality_gates.yaml thresholds have a documented origin instead of unexamined defaults
allowed-tools:
  - Read
  - Write
  - Bash(python3:*)
  - Bash(test:*)
when_to_use: >
  Use BEFORE `new-service` / `new-service.sh` / `copier copy` for any new
  ML service. Examples: 'spec out this new service before scaffolding
  it', 'what's the fairness attribute for this model', 'capture the
  problem definition first', 'why is the quality gate threshold 0.80'.
argument-hint: "<service-slug>"
arguments:
  - service_slug
authorization_mode:
  interview: AUTO
  write_spec_file: AUTO              # local file, no secrets, gitignored by convention
  validate_schema: AUTO
  escalation_triggers:
    - fairness_attribute_declared_none: CONSULT  # confirm deliberately, never silently skip
    - invalid_schema: STOP
---

# New-Service-Spec — Capture the ML Problem Before Scaffolding

## When to use

Before scaffolding a new service. `new-service.sh` / `copier copy`
capture *technical* parameters (name, slug, cloud) but nothing about the
*problem* the model solves — so `quality_gates.yaml` ships with default
thresholds nobody examined against a real label, a real fairness
attribute, or a real cost of getting it wrong. This skill closes that
gap the same way `template-onboard` closes the infra-wiring gap: an
interview, before code exists, written to a file the rest of the
pipeline can read.

## When NOT to use

- **After scaffolding** — by then `quality_gates.yaml` already has
  placeholder thresholds; use this first, or accept you're retrofitting.
- **To store secrets or PII** — this skill captures a problem
  *definition* (what the label means, which attribute is sensitive), never
  real customer data or examples containing it.

## Pre-conditions

None — this runs before the service directory exists. Output is a
standalone file the adopter carries into the `new-service` skill/workflow.

## Steps

### Step 1 — Interview (AUTO)

Ask the following. An unanswered question is written as `null`, never
guessed — a guessed fairness attribute is worse than an honest `null`
that a later reviewer must explicitly confirm.

1. **Label / target**: what does the model predict, in one sentence?
   What does the positive class concretely mean (e.g. "customer churns
   within 90 days", not just "1")?
2. **Fairness-sensitive attribute(s)**: which attribute(s), if any,
   must not produce disparate impact (e.g. age band, gender, region)?
   If truly none apply, say so explicitly — this escalates to CONSULT
   (a deliberate "none" must be confirmed, not defaulted into).
3. **Cost asymmetry**: is a false negative or a false positive worse for
   this problem, and roughly how much worse (a ratio, even a rough one)?
   This is what a quality-gate threshold should trace back to.
4. **Data source**: where does training data come from, and what's its
   expected refresh cadence (daily, weekly, on-demand)?
5. **Minimum acceptable metric**: what score (and on what metric) is the
   floor for promoting a model at all? This becomes the starting point
   for `quality_gates.yaml`, not an arbitrary `0.80`.

### Step 2 — Write the spec file (AUTO)

Write `<service_slug>_service_spec.local.yaml` following
`templates/config/service_spec.example.yaml`. Add the file's directory
pattern to `.gitignore` if not already covered (same convention as
`*_context.local.yaml`).

### Step 3 — Validate against schema (AUTO)

```bash
python3 -c "
import json, yaml, jsonschema
schema = json.load(open('templates/config/service_spec.schema.json'))
data = yaml.safe_load(open('${service_slug}_service_spec.local.yaml'))
jsonschema.validate(data, schema)
print('Service spec valid')
"
```

If validation fails → **STOP** with the schema error.

### Step 4 — Report and hand off (AUTO)

Print a summary (label, fairness attribute or explicit "none — confirmed",
cost asymmetry, minimum metric) and point to the `new-service` skill /
`/new-service` workflow as the next step. The generated service's
`quality_gates.yaml` should cite this file's minimum-metric and
fairness-attribute answers instead of the template's bare defaults.

## What this skill does NOT do

- Does NOT scaffold the service — that's `new-service.sh` / `copier copy`.
- Does NOT write secrets or real PII — problem definitions only.
- Does NOT set the final `quality_gates.yaml` values — it documents the
  *origin* a human uses to set them deliberately.

## Invariants

- A fairness attribute of `null` MUST be an explicit, confirmed answer
  (CONSULT), never a silent default.
- The spec file MUST pass `service_spec.schema.json` before scaffolding
  proceeds.
- The skill NEVER guesses an unanswered field.

## Related

- Skill: `template-onboard` (the infra-wiring counterpart — cloud, registry, MLflow URI)
- Skill: `new-service` (consumes this spec's answers when scaffolding)
- Rule: `08-data-validation` (fairness DIR ≥ 0.80 gate this spec feeds)
- ADR-041 — Agentic skill/domain expansion (why this skill exists)
