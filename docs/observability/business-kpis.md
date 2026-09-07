# Observability — Business KPIs Mapping

- **Authority**: monitoring-stations audit (2026-07) — the Business KPIs
  station was the one genuine gap the audit found: `project_context.kpis[]`
  was defined but nothing consumed it.
- **Scope**: how `project_context.example.yaml`'s `kpis.business[]` list
  relates to `dashboard-business.json`, and — just as important — what
  it deliberately does NOT do.
- **Owner**: Product / Platform Engineering (joint).

---

## Why this document exists

`project_context.example.yaml` asks every adopter to declare business
KPIs (`kpis.business[]`, each with a `name`, `direction`, `owner`, and
optional `minimum`). Before this audit, nothing read that list — it
fed the agentic release-gate logic (via `agentic_policy`) but had zero
presence in Grafana. A reviewer could not answer "where do I see the
business impact of this service?" without opening the YAML.

## What maps directly (no adopter work required)

These `dashboard-business.json` panels are computed from data the
template already collects — they work the moment the service is
scaffolded, with no adopter-side wiring:

| Panel | Source | Proxies for |
| --- | --- | --- |
| Request Volume (daily) | `{service}_requests_total` (FastAPI app) | Traffic / usage — the closest generic proxy for "how many people/systems rely on this" without knowing the adopter's actual unit of business volume. |
| SLA Compliance (30d) | `{service}:sli:availability` recording rule (already computed for the SLO burn-rate alerts) | Reliability as the business sees it — a longer window and a business-legible unit (%), not a new metric. |
| Predictions by Risk Level | `{service}_predictions_total` by `risk_level` | Segment mix — is the model's output distribution shifting over time. |
| Error Rate impact on users | `{service}_requests_total{status="500"}` (count, not rate) | Concrete, business-legible failure volume. |

## What requires one adopter step

| Panel | What's needed |
| --- | --- |
| Monthly Cloud Cost vs. Budget | The `cost-audit` skill's Pushgateway step (see its SKILL.md "Step 2b") must run at least once — monthly cadence, matching the skill's own review cycle. The panel's yellow/red thresholds are a manually-set Grafana field value; update them to match your `company_context.monthly_budget_usd` after scaffolding. This is a **manual sync, not an automatic one** — see "What this deliberately does not do" below for why. |

## What this deliberately does NOT do

**`kpis.business[].name` is not rendered generically.** A `project_context`
can declare an arbitrary business metric (`"monthly_active_users"`,
`"loan_approval_rate"`, `"cart_abandonment_delta"` — anything). At
template-authoring time there is no way to know:

- Whether that metric is even a Prometheus series, or lives in a data
  warehouse, a weekly CSV export, or a BI tool.
- Its unit, expected range, or whether higher/lower is "urgent."

Building a dashboard panel that assumes a shape for an unspecified
metric would produce a panel that's either empty (no matching series)
or, worse, silently wrong (matches an unrelated series with a similar
name). Per this template's own claim discipline (see `ADR-038` for the
same reasoning applied to compliance mapping): an honest gap beats a
fake panel.

**If your business KPI is a real Prometheus metric**: add a panel to
`dashboard-business.json` referencing it directly — the file is a
normal Grafana JSON model, not a generated artifact.

**If it is not a Prometheus metric** (the common case — most true
business KPIs live in a warehouse or BI tool, not in your service's
`/metrics` endpoint): it does not belong on a live ops dashboard at
all. Pull it into whatever periodic business review your organization
already runs; wiring a warehouse query into Grafana just to have one
more panel is the over-engineering this template's Engineering
Calibration Principle (`CLAUDE.md`) already warns against.

## Related

- `docs/observability/dashboards-inventory.md` — the dashboard,
  panel-by-panel, and its Prometheus dependencies.
- `templates/config/project_context.example.yaml` — where
  `kpis.business[]` is declared.
- `agentic/skills/cost-audit/SKILL.md` — the Pushgateway wiring for the
  one panel that needs it.
- `docs/decisions/ADR-038-compliance-mapping.md` — the same
  descriptive-not-certifying discipline applied to a different domain.
