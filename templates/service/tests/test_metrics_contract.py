"""Tests for the metrics contract (Phase 1.3).

Goal: every Prometheus metric referenced in alert/rule YAML files has a
corresponding `Counter | Gauge | Histogram` declaration in the service
code (or is on the standard external allow-list). Catches:

- An alert that references `{service}_request_duration_secs` (typo: missing
  `_seconds` suffix).
- A metric renamed in `fastapi_app.py` without updating the SLO rule.
- A new alert that points at a metric that does not exist yet.

The test is YAML- and source-only — no Prometheus runtime needed. It runs
in milliseconds and is wired into the scaffold smoke chain.

## Method

1. Parse `app/fastapi_app.py` and `src/<service>/monitoring/{drift_detection,performance_monitor}.py`
   for every `Counter(...) | Gauge(...) | Histogram(...)` constructor and
   capture the metric name (first positional arg, after stripping
   placeholder/format).
2. Parse every `expr:` block in the alert/rule YAMLs and pull bare
   identifiers that look like metrics (heuristic: leading word followed
   by `(`, `{`, `[`, whitespace, or end of expression — excluding PromQL
   keywords and functions).
3. Assert that each extracted reference is either declared by step 1 or
   on the explicit external allow-list (kube_*, container_*, up).

The intent is not 100% PromQL parsing — that requires `promtool`, which
this test deliberately does NOT depend on (the project does not pin a
Prometheus binary). It is a defensive lower bound that catches the
common drift mode (rename without rule update) at PR time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# Repo root resolved relative to this test file.
REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Heuristic extractors
# ---------------------------------------------------------------------------
# Matches a `Counter("foo", ...)` / `Gauge("bar", ...)` / `Histogram("baz", ...)`
# constructor. The metric name is captured from the first positional argument.
# We accept either:
#   - a literal string:   Counter("svc_requests_total", ...)
#   - an f-string:        Counter(f"{_PREFIX}_requests_total", ...)
#   - a placeholder:      Gauge("{service}_psi_score", ...)
# In the f-string case, we replace `{<expr>}` with the literal token
# `__PREFIX__` so we can match `<service>_*` references without having
# to evaluate Python.
_METRIC_DECL = re.compile(
    r"\b(?:Counter|Gauge|Histogram)\s*\(\s*f?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)

# Matches a bare identifier that *might* be a metric. PromQL identifiers
# match [A-Za-z_:][A-Za-z0-9_:]*. We then filter against the function
# allow-list to drop `rate(...)`, `sum(...)`, etc.
_PROMQL_IDENT = re.compile(r"\b([A-Za-z_:][A-Za-z0-9_:]*)\b")

# PromQL functions and keywords that can appear at the head of an
# identifier-like token but are not metrics. Add new ones here, never
# inline as a magic string elsewhere.
_PROMQL_NON_METRICS = frozenset(
    {
        "abs",
        "ago",
        "and",
        "atan2",
        "avg",
        "avg_over_time",
        "bool",
        "by",
        "ceil",
        "changes",
        "clamp",
        "clamp_max",
        "clamp_min",
        "count",
        "count_over_time",
        "count_values",
        "day_of_month",
        "day_of_week",
        "delta",
        "deriv",
        "exp",
        "floor",
        "for",
        "group",
        "group_left",
        "group_right",
        "histogram_quantile",
        "holt_winters",
        "hour",
        "idelta",
        "ignoring",
        "increase",
        "irate",
        "label_join",
        "label_replace",
        "ln",
        "log10",
        "log2",
        "max",
        "max_over_time",
        "min",
        "min_over_time",
        "minute",
        "month",
        "offset",
        "on",
        "or",
        "predict_linear",
        "quantile",
        "quantile_over_time",
        "rate",
        "resets",
        "round",
        "scalar",
        "sgn",
        "sort",
        "sort_desc",
        "sqrt",
        "stddev",
        "stddev_over_time",
        "stdvar",
        "stdvar_over_time",
        "sum",
        "sum_over_time",
        "time",
        "timestamp",
        "topk",
        "unless",
        "vector",
        "without",
        "year",
        # PromQL label-set keywords used in match arguments
        "le",
        "endpoint",
        "status",
        "container",
        "feature",
        "job",
        "instance",
        "service",
        "severity",
        "model_version",
        "risk_level",
        "version",
        "true",
        "false",
        # Numeric literals tokenised as words (rarely appear)
        "Inf",
        "NaN",
    }
)

# External (kubernetes / cAdvisor / kube-state) metrics referenced by
# alerts but emitted by other components, not the service itself.
EXTERNAL_METRICS = frozenset(
    {
        "up",
        "container_cpu_usage_seconds_total",
        "container_spec_cpu_quota",
        "container_spec_cpu_period",
        "kube_pod_container_status_restarts_total",
    }
)


_HISTOGRAM_DECL = re.compile(
    r"\bHistogram\s*\(\s*f?[\"']([^\"']+)[\"']",
    re.MULTILINE,
)


def _extract_declared_metrics() -> set[str]:
    """Walk known service modules and pull every declared metric name.

    Replaces every `{...}` placeholder (whether f-string interpolation or
    pre-scaffolder literal) with a sentinel `<PFX>` so a declared name
    `f"{_METRIC_PREFIX}_requests_total"` is normalised to
    `<PFX>_requests_total`. References in YAML get the same
    normalisation, so we compare on the suffix only.

    For Histograms we also expand the auto-emitted suffixes
    ``_bucket``, ``_count``, and ``_sum`` because Prometheus exposes
    those derived names and alert exprs reference them directly.
    """
    sources = [
        REPO_ROOT / "app" / "fastapi_app.py",
        REPO_ROOT / "src" / "{service}" / "monitoring" / "drift_detection.py",
        REPO_ROOT / "src" / "{service}" / "monitoring" / "performance_monitor.py",
    ]
    # Service-name placeholder may have been substituted by the scaffolder
    # already (test_scaffold.sh runs `sed s/{service}/test_svc/g`). Try the
    # generic and the substituted layout; whichever exists wins.
    rendered_root = REPO_ROOT / "src"
    for child in rendered_root.iterdir() if rendered_root.is_dir() else []:
        if child.is_dir() and child.name not in {"{service}", "__pycache__"}:
            sources.append(child / "monitoring" / "drift_detection.py")
            sources.append(child / "monitoring" / "performance_monitor.py")

    declared: set[str] = set()
    histogram_bases: set[str] = set()
    for path in sources:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for raw in _METRIC_DECL.findall(text):
            declared.add(_normalise_metric_name(raw))
        for raw in _HISTOGRAM_DECL.findall(text):
            histogram_bases.add(_normalise_metric_name(raw))
    for base in histogram_bases:
        declared.add(f"{base}_bucket")
        declared.add(f"{base}_count")
        declared.add(f"{base}_sum")
    return declared


def _normalise_metric_name(name: str) -> str:
    """Replace `{...}` placeholders with a single sentinel."""
    return re.sub(r"\{[^}]*\}", "<PFX>", name)


def _extract_referenced_metrics(yaml_path: Path) -> set[str]:
    """Pull every PromQL metric reference from the YAML's `expr:` blocks.

    The PrometheusRule schema nests rules under `spec.groups[*].rules[*]`
    OR under `groups[*].rules[*]` (alertmanager-rules.yaml uses the
    latter). Both shapes are scanned.
    """
    text = yaml_path.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(text))
    refs: set[str] = set()
    for doc in docs:
        if not doc:
            continue
        groups = []
        if isinstance(doc, dict):
            if "groups" in doc:
                groups = doc["groups"]
            elif "spec" in doc and isinstance(doc["spec"], dict) and "groups" in doc["spec"]:
                groups = doc["spec"]["groups"]
        for group in groups or []:
            for rule in group.get("rules", []) or []:
                expr = rule.get("expr", "")
                if not isinstance(expr, str):
                    continue
                refs.update(_idents_from_expr(expr))
    return refs


def _strip_quoted(expr: str) -> str:
    """Remove the contents of double- and single-quoted strings.

    Label-matcher RHS values like ``status="500"``, ``container="svc-predictor"``
    or ``job="svc-drift-detection"`` would otherwise leak into the
    identifier extraction and produce false positives like ``predictor``,
    ``drift``, ``detection``. The replacement keeps the quotes themselves
    so the surrounding tokenisation is unaffected.
    """
    expr = re.sub(r'"[^"]*"', '""', expr)
    expr = re.sub(r"'[^']*'", "''", expr)
    return expr


def _idents_from_expr(expr: str) -> set[str]:
    """Extract metric-like identifiers from a PromQL expression.

    Heuristic: keep tokens that satisfy ALL of:
      * Match the PromQL identifier shape.
      * Are NOT in the PromQL function/keyword allow-list.
      * Are NOT pure numeric.
      * Are NOT recording-rule names containing ':' (those are
        cross-references to other recorded SLIs — checked separately).
      * Do not appear inside a quoted string (label-matcher value).
    """
    cleaned = _strip_quoted(expr)
    out: set[str] = set()
    for tok in _PROMQL_IDENT.findall(cleaned):
        if tok in _PROMQL_NON_METRICS:
            continue
        if tok.isdigit():
            continue
        if ":" in tok:
            # Recording-rule cross-reference; tracked elsewhere.
            continue
        out.add(_normalise_metric_name(tok))
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
ALERT_YAMLS = [
    REPO_ROOT / "k8s" / "base" / "slo-prometheusrule.yaml",
    REPO_ROOT / "monitoring" / "alertmanager-rules.yaml",
]


@pytest.fixture(scope="module")
def declared_metrics() -> set[str]:
    return _extract_declared_metrics()


@pytest.mark.parametrize("yaml_path", ALERT_YAMLS, ids=lambda p: p.name)
def test_alert_metric_references_have_declarations(declared_metrics: set[str], yaml_path: Path) -> None:
    """Every metric named in alert exprs is declared somewhere or external."""
    if not yaml_path.is_file():
        pytest.skip(f"{yaml_path.name} not present in scaffolded layout")
    refs = _extract_referenced_metrics(yaml_path)
    if not refs:
        pytest.skip(f"no metric references found in {yaml_path.name}")

    unknown = []
    for ref in sorted(refs):
        if ref in EXTERNAL_METRICS:
            continue
        # Match either the literal name or a `<PFX>_*` shape against
        # any declared metric. The placeholder can be present in
        # either side; we check the suffix after the first `_`.
        if ref in declared_metrics:
            continue
        # Tolerate prefix mismatches: declarations capture the f-string
        # head as ``<PFX>_<suffix>`` (because we cannot evaluate Python
        # at parse time) while the YAML may already be rendered with
        # the literal service name (the scaffolder substitutes
        # ``{service}`` → e.g. ``test_svc``). Match on suffix instead.
        prefixed_suffixes = {m[len("<PFX>") :] for m in declared_metrics if m.startswith("<PFX>")}
        if any(ref.endswith(s) for s in prefixed_suffixes):
            continue
        unknown.append(ref)

    assert not unknown, (
        f"\n{yaml_path.name} references metrics with no declaration:\n  - "
        + "\n  - ".join(unknown)
        + "\n\nDeclared metrics:\n  - "
        + "\n  - ".join(sorted(declared_metrics))
        + "\n\nFix: either declare the metric in app/fastapi_app.py / "
        "src/<service>/monitoring/, add it to EXTERNAL_METRICS in this "
        "test (if emitted by k8s/cadvisor/kube-state-metrics), or "
        "remove the alert."
    )


def test_recording_rule_cross_references_resolve() -> None:
    """A recording rule referenced by an alert must itself exist.

    The SLO file declares records like ``{service}:sli:availability``
    and then references them in alert exprs. If the alert names a
    record that was renamed but not retained, Prometheus silently
    evaluates to NaN and the alert never fires.
    """
    slo_path = REPO_ROOT / "k8s" / "base" / "slo-prometheusrule.yaml"
    if not slo_path.is_file():
        pytest.skip("slo-prometheusrule.yaml not present")
    text = slo_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    spec = doc.get("spec", {})

    declared_records: set[str] = set()
    referenced_records: set[str] = set()
    for group in spec.get("groups", []) or []:
        for rule in group.get("rules", []) or []:
            if "record" in rule:
                declared_records.add(_normalise_metric_name(rule["record"]))
            expr = rule.get("expr", "") or ""
            for tok in _PROMQL_IDENT.findall(expr):
                if ":" in tok:
                    referenced_records.add(_normalise_metric_name(tok))

    missing = referenced_records - declared_records
    assert not missing, f"alerts reference undefined recording rules: {sorted(missing)}"


def test_every_alert_has_runbook_url() -> None:
    """Every alert must carry a ``runbook_url`` annotation (Phase 1.3
    standardisation). On-call cannot triage from a summary alone.
    """
    missing: list[str] = []
    for yaml_path in ALERT_YAMLS:
        if not yaml_path.is_file():
            continue
        doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        groups = (doc or {}).get("spec", {}).get("groups") or (doc or {}).get("groups") or []
        for group in groups:
            for rule in group.get("rules", []) or []:
                if "alert" not in rule:
                    continue
                annotations = rule.get("annotations") or {}
                if not annotations.get("runbook_url"):
                    missing.append(f"{yaml_path.name}::{rule['alert']}")
    assert not missing, "alerts missing runbook_url annotation:\n  - " + "\n  - ".join(missing)
