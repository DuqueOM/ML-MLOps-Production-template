# Alertmanager routing validation runbook

**Authority**: ADR-020 §M5, ACTION_PLAN_R4 §S2-4.
**Automated by**: `templates/service/monitoring/tests/test_alertmanager_routing.py`
**Config under test**: `templates/service/monitoring/alertmanager.yml`
**Rules emitting alerts**: `templates/service/monitoring/alertmanager-rules.yaml`

This runbook closes R4-M5: before M5, the template shipped alert rules
but no one had ever exercised routing end-to-end. A mis-configured
`receiver:` reference would fire during a real incident and go nowhere.

---

## 1. When to run this

**Always** as part of the CI pipeline — the pytest suite is structural
and runs in < 1 s. The human-in-the-loop procedure below is only for:

- **Onboarding** — a new adopter copying the template into their cluster.
- **Config changes** — any PR that edits `alertmanager.yml` must have a
  reviewer run the manual `amtool` check against a staging Alertmanager.
- **Incident post-mortem** — a P1 that did not page is a routing failure
  until proven otherwise.

---

## 2. Expected routing table (contract)

| Priority | Alert labels | Receiver | Latency SLA |
| ---------: | ------------------------------------------------ | -------------------- | ------------- |
| P1 | `severity=critical`, `action=page` | `oncall-pager` | < 2 min |
| P2 | `severity=warning`, `action=ticket` | `platform-tickets` | < 1 h |
| P3 | `severity=warning`, `action=retrain` | `ml-retrain` | < 24 h |
| P4 | `severity=info`, `action=heartbeat` | `ops-chat` | best-effort |
| default | (anything else) | `ops-chat` | best-effort |

The pytest suite asserts every row via **two independent paths**:
`amtool config routes test` (authoritative) + a pure-Python simulator
(always-runs fallback). Both must agree — divergence means either the
simulator or the config has drifted from Alertmanager's semantics.

---

## 3. Quick validation (30 seconds)

```bash
# From repo root, assuming amtool is on PATH or unpacked locally.
python -m pytest templates/service/monitoring/tests/test_alertmanager_routing.py -q
# 14 passed
```

If any row fails, **stop** and inspect:

- **Simulator fails + amtool passes** → the simulator fell behind Alertmanager's
  matcher semantics; update `_parse_matcher` or `_route_matches` in the test.
- **amtool fails + simulator passes** → the config is ambiguous; `amtool` is
  the source of truth. Re-read `alertmanager.yml` until the authoritative
  tool routes the way you expect.
- **Both fail** → someone changed the routing and forgot to update
  `ROUTING_MATRIX`. Either revert or update both in the same PR.

---

## 4. Installing `amtool`

`amtool` ships with Alertmanager. The repo's `.gitignore` tolerates a
local unpack directory so contributors can validate without Docker.

```bash
curl -sSL -o am.tgz \
  https://github.com/prometheus/alertmanager/releases/download/v0.25.0/alertmanager-0.25.0.linux-amd64.tar.gz
tar -xzf am.tgz
./alertmanager-0.25.0.linux-amd64/amtool --version
# amtool, version 0.25.0 ...
```

The pytest suite auto-discovers the binary at:

1. `$PATH` (preferred for CI images).
2. `<repo>/alertmanager-*/amtool` (local contributor convenience).

If neither is present, the **amtool-authoritative tests skip cleanly**
and the simulator tests still assert the contract.

---

## 5. Manual end-to-end validation (against a real cluster)

Run this before promoting any alertmanager config change to production.
It injects a synthetic alert via Alertmanager's HTTP API and asserts
that the real receiver got hit.

```bash
NS=mlops-staging
AM_URL="http://$(kubectl -n $NS get svc alertmanager -o jsonpath='{.spec.clusterIP}'):9093"

# 1. Fire a synthetic P1.
amtool --alertmanager.url="$AM_URL" alert add \
  alertname=SyntheticP1 \
  severity=critical action=page service=synthetic \
  --annotation="summary=routing-validation synthetic alert"

# 2. Confirm it routed to oncall-pager (amtool queries the active alerts
#    AND the receiver they notified).
amtool --alertmanager.url="$AM_URL" alert query severity=critical

# 3. Silence it so you don't wake anyone at 03:00.
amtool --alertmanager.url="$AM_URL" silence add \
  alertname=SyntheticP1 \
  --duration=5m --comment="routing-validation cleanup"
```

Repeat steps 1-3 for each priority row in §2. On-call must confirm that
the **real** PagerDuty / Slack / Jira receiver fired.

---

## 6. What this runbook does NOT cover

- **Webhook endpoint health** — whether PagerDuty / Slack actually
  delivered the notification. That is adopter-owned (depends on the
  real webhook URLs configured in the adopter's overlay).
- **Template rendering** — `alertmanager.yml` references
  `/etc/alertmanager/templates/*.tmpl` but the template bundle itself
  is out of scope for M5.
- **Rule correctness** — whether the Prometheus expressions in
  `alertmanager-rules.yaml` fire at the right time. Covered by
  `docs/runbooks/drift-detection.md` and the PSI threshold ADR.
- **Inhibit-rule end-to-end** — §2 locks the rule structure; actual
  suppression during a P1 storm is exercised during chaos testing
  (backlogged — see ACTION_PLAN_R4 §8).

---

## 7. Audit trail

Every manual run of §5 should produce an `ops/audit.jsonl` entry via:

```bash
python scripts/audit_record.py \
  --agent alertmanager-validation \
  --operation "routing_smoke_test" \
  --environment staging \
  --base-mode CONSULT \
  --final-mode CONSULT \
  --result success \
  --approver "<your handle>" \
  --inputs '{"labels":"severity=critical,action=page","receiver_expected":"oncall-pager"}' \
  --outputs '{"receiver_observed":"oncall-pager","latency_s":8}'
```

The pytest run is AUTO — no audit entry required.

---

## 8. Related

- `templates/service/monitoring/alertmanager.yml` — the config under test.
- `templates/service/monitoring/alertmanager-rules.yaml` — the alert rules.
- `templates/service/monitoring/tests/test_alertmanager_routing.py` — the
  contract test (14 invariants).
- ADR-020 §M5 — rationale for why this runbook exists.
- ADR-014 §3.5 — audit-trail protocol referenced in §7.
