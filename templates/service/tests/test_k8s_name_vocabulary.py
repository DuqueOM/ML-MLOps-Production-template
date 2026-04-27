"""PR-A5b — K8s name vocabulary contract.

Background
----------

The template ships two placeholder vocabularies:

- ``{service}`` — snake_case slug. Used for Python identifiers,
  Prometheus metric names, recording-rule prefixes, and the
  ``SERVICE_METRIC_PREFIX`` env var read by ``app/fastapi_app.py``.
- ``{service-name}`` — kebab-case slug (snake_case with ``_`` → ``-``).
  Used for every Kubernetes resource name, namespace, label value,
  service-account name, image ref, IRSA/Workload-Identity annotation,
  URL path, and Prometheus AlertManager ``service:`` label that
  mirrors a K8s name.

The split is dictated by RFC 1123 — Kubernetes resource names cannot
contain ``_``. With a slug like ``golden_path`` the legacy single-
placeholder layout produced names such as ``golden_path-dev`` which
``kustomize build`` rejected with the canonical error::

    Invalid value: "golden_path-dev": a lowercase RFC 1123 label
    must consist of lower case alphanumeric characters or '-'

This test prevents that regression by enforcing two layers:

  1. **Static**: under ``k8s/`` and ``monitoring/`` no kebab-context
     occurrence of ``{service}`` may remain; the placeholder there
     MUST be ``{service-name}``. Catches a future contributor who
     adds a new K8s manifest using ``{service}`` in a ``name:``
     position without thinking about the vocabulary.

  2. **Rendered**: substitute the placeholders for a snake-heavy
     bug-trigger slug (``golden_path``) and assert that EVERY value
     extracted from the canonical K8s name positions matches the RFC
     1123 label regex. This is what kustomize/kubectl actually
     evaluate against, so the test is the same gate the real
     deployment is.

The test is YAML-only — no kustomize, no kubectl — and runs in
either the scaffolded layout (where placeholders are already
substituted) or the template-repo layout (where they aren't).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# RFC 1123 label: lowercase alphanumeric + hyphen, must start and end
# with alphanumeric, max 63 chars. K8s `metadata.name` for most
# resources allows a *subdomain* (multiple dot-separated labels) but
# every label segment must follow the label rule. Using the stricter
# label rule for `metadata.name` is fine because none of the template's
# names contain dots — keeping them dot-free is itself a hygiene rule.
_RFC1123_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_RFC1123_LABEL_MAX = 63

# Bug-trigger slug used for the rendered-layer check. Snake-heavy on
# purpose: every `_` that survives substitution into a kebab context
# becomes a violation.
SAMPLE_SNAKE = "golden_path"
SAMPLE_KEBAB = "golden-path"

# Discovery — same dual-layout convention as PR-C2.
_THIS = Path(__file__).resolve()
_CANDIDATE_PREFIXES = [_THIS.parents[1], _THIS.parents[2]]
_DISCOVERY_ROOTS = [
    prefix / sub
    for prefix in _CANDIDATE_PREFIXES
    for sub in ("k8s", "monitoring")
    if (prefix / sub).is_dir()
]


def _iter_yaml_files() -> list[Path]:
    out: list[Path] = []
    for root in _DISCOVERY_ROOTS:
        for ext in ("*.yaml", "*.yml"):
            out.extend(sorted(root.rglob(ext)))
    return out


_ALL_YAMLS = _iter_yaml_files()


# ---------------------------------------------------------------------------
# Layer 1 — Static: no `{service}` survives in a kebab-required position
# ---------------------------------------------------------------------------

# Patterns that mark kebab-required positions. If any of these match a
# raw line containing `{service}` (without `-name`), the file has a
# vocabulary regression. The patterns are deliberately conservative —
# we only flag positions where K8s NAME semantics apply, never where
# the value is plausibly a Prometheus metric name or a Python ident.
_KEBAB_REGEXES = [
    # Resource names.
    re.compile(r'^\s*name:\s*"\{service\}'),
    re.compile(r'^\s*name:\s*\{service\}-'),
    # K8s `app:` and `service:` label values.
    re.compile(r'^\s*app:\s*"?\{service\}"?\s*$'),
    re.compile(r'^\s*service:\s*"\{service\}"\s*$'),
    # Prometheus selector that names the K8s service.
    re.compile(r'service="\{service\}"'),
    re.compile(r'job="\{service\}"'),
    # Anything that looks like a hyphen-suffixed K8s name.
    re.compile(r"\{service\}-[a-z]"),
    # URL/path style references that mirror K8s names.
    re.compile(r"/\{service\}/"),
]


@pytest.mark.parametrize(
    "yaml_path",
    _ALL_YAMLS or [pytest.param(None, marks=pytest.mark.skip(reason="no k8s/ or monitoring/ found"))],
    ids=lambda p: p.name if p else "skip",
)
def test_no_naked_service_placeholder_in_kebab_context(yaml_path: Path) -> None:
    """Every K8s-name position MUST use ``{service-name}``."""
    if yaml_path is None:
        pytest.skip("no manifests")
    text = yaml_path.read_text(encoding="utf-8")
    bad: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        for rx in _KEBAB_REGEXES:
            if rx.search(line):
                bad.append((n, line.rstrip()))
                break
    assert not bad, (
        f"{yaml_path}: kebab-context `{{service}}` placeholder found "
        f"(must be `{{service-name}}` per PR-A5b):\n"
        + "\n".join(f"  L{n}: {line}" for n, line in bad)
    )


# ---------------------------------------------------------------------------
# Layer 2 — Rendered: substitute and validate against RFC 1123
# ---------------------------------------------------------------------------


def _render(text: str) -> str:
    """Apply the same placeholder substitutions ``new-service.sh`` does,
    using a snake-heavy bug-trigger slug. Specific-first order so the
    kebab placeholder cannot be consumed by the snake substitution.
    """
    text = text.replace("{ServiceName}", "GoldenPath")
    text = text.replace("{service-name}", SAMPLE_KEBAB)
    text = text.replace("{service}", SAMPLE_SNAKE)
    text = text.replace("{SERVICE}", "GOLDEN_PATH")
    return text


def _is_k8s_doc(doc: object) -> bool:
    return isinstance(doc, dict) and "apiVersion" in doc and "kind" in doc


def _collect_names(doc: dict) -> list[tuple[str, str]]:
    """Return ``[(json_pointer, value), ...]`` for every position whose
    value is constrained to RFC 1123 labels.

    Coverage:
      - ``metadata.name``
      - ``metadata.namespace`` (if set)
      - ``metadata.labels.app`` and ``metadata.labels.service`` (the
        two label keys the templates actually populate with K8s-name-
        derived values; other label values like ``managed-by`` are
        free-form by design)
      - ``spec.serviceAccountName``
      - ``spec.template.spec.serviceAccountName``
      - ``spec.template.spec.containers[*].name``
      - Container ``initContainers[*].name``
      - ``spec.selector.matchLabels.app`` and similar
      - ``subjects[*].name`` for RoleBinding / ClusterRoleBinding
      - ``roleRef.name`` for RoleBinding
    """
    out: list[tuple[str, str]] = []
    md = doc.get("metadata") or {}
    if isinstance(md, dict):
        for k in ("name", "namespace"):
            v = md.get(k)
            if isinstance(v, str):
                out.append((f"metadata.{k}", v))
        labels = md.get("labels") or {}
        if isinstance(labels, dict):
            for lk in ("app", "service"):
                v = labels.get(lk)
                if isinstance(v, str):
                    out.append((f"metadata.labels.{lk}", v))

    spec = doc.get("spec") or {}
    if isinstance(spec, dict):
        for k in ("serviceAccountName",):
            v = spec.get(k)
            if isinstance(v, str):
                out.append((f"spec.{k}", v))
        # Pod-template containers.
        tmpl = (spec.get("template") or {}).get("spec") or {}
        if isinstance(tmpl, dict):
            v = tmpl.get("serviceAccountName")
            if isinstance(v, str):
                out.append(("spec.template.spec.serviceAccountName", v))
            for ctype in ("initContainers", "containers"):
                for i, c in enumerate(tmpl.get(ctype, []) or []):
                    if isinstance(c, dict) and isinstance(c.get("name"), str):
                        out.append((f"spec.template.spec.{ctype}[{i}].name", c["name"]))
        # CronJob nesting: spec.jobTemplate.spec.template.spec.{init,}containers[*].name
        job_tmpl = ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template", {}).get("spec") or {}
        if isinstance(job_tmpl, dict):
            v = job_tmpl.get("serviceAccountName")
            if isinstance(v, str):
                out.append(("spec.jobTemplate.spec.template.spec.serviceAccountName", v))
            for ctype in ("initContainers", "containers"):
                for i, c in enumerate(job_tmpl.get(ctype, []) or []):
                    if isinstance(c, dict) and isinstance(c.get("name"), str):
                        out.append(
                            (f"spec.jobTemplate.spec.template.spec.{ctype}[{i}].name", c["name"])
                        )
        # Selector matchLabels.
        sel = spec.get("selector")
        if isinstance(sel, dict):
            ml = sel.get("matchLabels") or {}
            if isinstance(ml, dict):
                for lk in ("app", "service"):
                    v = ml.get(lk)
                    if isinstance(v, str):
                        out.append((f"spec.selector.matchLabels.{lk}", v))

    # RoleBinding / ClusterRoleBinding.
    for i, sub in enumerate(doc.get("subjects", []) or []):
        if isinstance(sub, dict) and isinstance(sub.get("name"), str):
            out.append((f"subjects[{i}].name", sub["name"]))
    rr = doc.get("roleRef")
    if isinstance(rr, dict) and isinstance(rr.get("name"), str):
        out.append(("roleRef.name", rr["name"]))
    return out


def _rfc1123_violations(name: str) -> str | None:
    if len(name) > _RFC1123_LABEL_MAX:
        return f"length {len(name)} > {_RFC1123_LABEL_MAX}"
    if not _RFC1123_LABEL.match(name):
        return "does not match ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
    return None


@pytest.mark.parametrize(
    "yaml_path",
    [p for p in _ALL_YAMLS if "k8s" in p.parts]
    or [pytest.param(None, marks=pytest.mark.skip(reason="no k8s/ found"))],
    ids=lambda p: p.name if p else "skip",
)
def test_rendered_k8s_names_are_rfc1123(yaml_path: Path) -> None:
    """Render placeholders with a snake-heavy slug and validate every
    K8s-name position against RFC 1123.
    """
    if yaml_path is None:
        pytest.skip("no manifests")
    rendered = _render(yaml_path.read_text(encoding="utf-8"))
    try:
        docs = list(yaml.safe_load_all(rendered))
    except yaml.YAMLError as exc:
        pytest.fail(f"{yaml_path}: rendered YAML is invalid: {exc}")

    bad: list[str] = []
    for doc in docs:
        if not _is_k8s_doc(doc):
            continue
        for ptr, value in _collect_names(doc):
            err = _rfc1123_violations(value)
            if err:
                bad.append(f"{ptr}={value!r}: {err}")
    assert not bad, (
        f"{yaml_path}: rendered K8s names violate RFC 1123 (slug={SAMPLE_SNAKE!r}):\n"
        + "\n".join(f"  - {b}" for b in bad)
        + "\n\nFix: change the offending position from `{service}` to "
        "`{service-name}` so the scaffolder substitutes the kebab variant."
    )


# ---------------------------------------------------------------------------
# Sanity: discovery isn't silently empty
# ---------------------------------------------------------------------------


def test_discovery_finds_canonical_manifests() -> None:
    assert _ALL_YAMLS, (
        f"no manifests discovered under {[str(r) for r in _DISCOVERY_ROOTS]}"
    )
    names = {p.name for p in _ALL_YAMLS}
    expected = {
        "deployment.yaml",
        "service.yaml",
        "serviceaccount.yaml",
        "rbac.yaml",
        "hpa.yaml",
        "pdb.yaml",
        "kustomization.yaml",
        "slo-prometheusrule.yaml",
        "performance-prometheusrule.yaml",
    }
    missing = expected - names
    assert not missing, f"discovery missed canonical manifests: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Self-check: the bug-trigger slug actually trips RFC 1123 in the
# unfixed form. If THIS test ever passes against `{service}` in a
# kebab context, the regex is wrong.
# ---------------------------------------------------------------------------


def test_bug_trigger_slug_actually_violates_rfc1123() -> None:
    """Sanity check: ``golden_path-dev`` MUST fail RFC 1123, otherwise
    the test is asserting against a too-loose regex."""
    assert _rfc1123_violations(f"{SAMPLE_SNAKE}-dev") is not None, (
        "golden_path-dev unexpectedly matches RFC 1123 — test regex is wrong"
    )
    assert _rfc1123_violations(SAMPLE_KEBAB) is None, (
        "golden-path unexpectedly fails RFC 1123 — test regex is wrong"
    )
