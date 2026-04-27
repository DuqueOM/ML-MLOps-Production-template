"""Lazy resolver for the service's Pandera ``ServiceInputSchema``.

Why a separate module
=====================

The Pandera schema is the *single source of truth* for input validation
(training, serving, drift — see ADR-016 PR-R2-4). It lives under
``src/{service}/schemas.py`` because that is where ``train.py`` consumes
it via a relative import.

The FastAPI router in :mod:`app.fastapi_app` cannot ``from
{service}.schemas import ServiceInputSchema`` directly: at template-test
time the package name is the literal placeholder ``{service}`` (not a
valid Python identifier) and the import fails at *parse* time, before
any ``try`` block can rescue it.

This module performs the resolution at *runtime* using
:func:`importlib.import_module`, controlled by the ``SERVICE_PACKAGE``
environment variable. After ``new-service.sh`` rewrites the project,
``SERVICE_PACKAGE`` defaults to the rendered slug; before scaffolding,
the resolution fails silently and ``ServiceInputSchema`` is ``None`` —
the validators in :mod:`common_utils.input_validation` treat ``None`` as
a no-op so structural tests still pass.

Operational contract
====================

* In a scaffolded service running in production, ``ServiceInputSchema``
  MUST resolve to the Pandera class. The CI lint added in PR-R2-4
  (``validate-templates.yml``) verifies that ``fastapi_app.py``
  references ``ServiceInputSchema`` and that ``drift_detection.py``
  imports it via the relative path; together these guarantee the
  contract is enforced everywhere it matters.
* The fallback to ``None`` is reserved for the unrendered template +
  structural unit tests. A real deploy is expected to set
  ``SERVICE_PACKAGE`` (Helm + Kustomize do this automatically via the
  ConfigMap). The :func:`get_pandera_schema` accessor logs a single
  warning when it falls back so that misconfigured deploys are visible
  in the pod log.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


_DEFAULT_PACKAGE = "{service}"  # rewritten by new-service.sh; see module docstring
_SCHEMA_ATTR = "ServiceInputSchema"


def _resolve() -> Optional[Any]:
    """Best-effort import of the Pandera schema.

    Returns ``None`` on any failure (missing package, missing attribute,
    Pandera not installed). Failures are logged at WARNING level so
    misconfigured deploys do not pass silently — the pod log is the
    operator's first stop after a 422 spike.
    """
    package = os.getenv("SERVICE_PACKAGE", _DEFAULT_PACKAGE)
    if not package or "{" in package:  # placeholder, not a real package name
        logger.warning(
            "Pandera schema unavailable: SERVICE_PACKAGE is unset or still "
            "the unrendered template placeholder (%r). /predict will run "
            "without the second validation wall — fine for template tests, "
            "BUG in a real deploy. See PR-R2-4 / ADR-016.",
            package,
        )
        return None
    try:
        module = importlib.import_module(f"{package}.schemas")
    except ImportError as exc:
        logger.warning(
            "Pandera schema package %r not importable (%s). Validation "
            "will be skipped at /predict; investigate before promoting.",
            package,
            exc,
        )
        return None
    schema = getattr(module, _SCHEMA_ATTR, None)
    if schema is None:
        logger.warning(
            "Module %s.schemas exists but exposes no %s attribute. " "Restore the contract or rename the schema class.",
            package,
            _SCHEMA_ATTR,
        )
    return schema


# Resolved once at import time; pods are short-lived enough that this
# does not need a refresh path. Hot-reload of the schema would change
# the contract under live traffic, which is exactly what we don't want.
ServiceInputSchema: Optional[Any] = _resolve()


def get_pandera_schema() -> Optional[Any]:
    """Public accessor used by the validators. Returns ``None`` only when
    the resolver failed (logged at import time)."""
    return ServiceInputSchema


__all__ = ["ServiceInputSchema", "get_pandera_schema"]
