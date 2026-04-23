"""Cloud-native secret loader with environment-aware resolution.

Usage (production code):
    from common_utils.secrets import get_secret

    api_key = get_secret("EXTERNAL_API_KEY")
    db_creds = get_secret("DB_PASSWORD", namespace="fraud-detector")

Resolution order (configured via ENV environment variable):
    - local/dev: `.env.local` file (not committed)
    - ci:        `os.environ` (from GitHub Secrets)
    - staging:   AWS Secrets Manager / GCP Secret Manager (via IRSA/WI)
    - production: AWS Secrets Manager / GCP Secret Manager (via IRSA/WI, required)

Invariants enforced (D-17, D-18):
    - Never falls through to os.environ in staging/production
    - Never logs the secret value
    - Never falls back silently — raises on miss

ADR-001 compliance:
    - HashiCorp Vault is NOT supported here (explicitly deferred)
    - To use Vault: set SECRETS_BACKEND=vault and provide your own adapter
      (out of scope for this module)
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SecretNotFoundError(Exception):
    """Raised when a requested secret cannot be resolved in the current environment."""


class SecretBackendError(Exception):
    """Raised when the configured backend is unreachable or misconfigured."""


# ═══════════════════════════════════════════════════════════════════
# Environment detection
# ═══════════════════════════════════════════════════════════════════


def _detect_environment() -> str:
    """Return one of: local, ci, staging, production."""
    env = os.environ.get("ENV", "").lower()
    if env in {"local", "dev", "development"}:
        return "local"
    if env in {"ci", "test"}:
        return "ci"
    if env in {"staging", "stage"}:
        return "staging"
    if env in {"production", "prod"}:
        return "production"

    # Fallback heuristics
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "ci"
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        # Running in K8s — assume staging unless overridden
        ns = os.environ.get("POD_NAMESPACE", "")
        return "production" if "prod" in ns else "staging"

    return "local"


def _detect_cloud() -> str:
    """Return one of: aws, gcp, unknown.

    Detection order:
    1. Explicit CLOUD_PROVIDER env var
    2. AWS presence (IRSA token path)
    3. GCP presence (metadata server env var)
    """
    explicit = os.environ.get("CLOUD_PROVIDER", "").lower()
    if explicit in {"aws", "gcp"}:
        return explicit
    if os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE"):
        return "aws"
    if os.environ.get("GCE_METADATA_HOST") or Path("/var/run/secrets/tokens").exists():
        return "gcp"
    return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Backends
# ═══════════════════════════════════════════════════════════════════


@functools.lru_cache(maxsize=1)
def _load_dotenv_local() -> dict[str, str]:
    """Parse .env.local from repo root. Returns {} if absent."""
    candidates = [Path.cwd() / ".env.local", Path(__file__).resolve().parent.parent / ".env.local"]
    for path in candidates:
        if path.exists():
            env: dict[str, str] = {}
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
            return env
    return {}


def _get_local(key: str) -> str:
    """Read from .env.local (dev convenience only)."""
    env = _load_dotenv_local()
    if key in env:
        return env[key]
    if key in os.environ:
        # Dev only — explicit os.environ fallback allowed locally
        return os.environ[key]
    raise SecretNotFoundError(f"{key} not in .env.local or os.environ (local mode)")


def _get_ci(key: str) -> str:
    """Read from os.environ (GitHub Secrets → workflow env → os.environ)."""
    if key in os.environ:
        return os.environ[key]
    raise SecretNotFoundError(f"{key} not in CI environment")


def _get_aws(key: str, namespace: str | None) -> str:
    """Read from AWS Secrets Manager via IRSA (D-18)."""
    try:
        import boto3
    except ImportError as e:
        raise SecretBackendError("boto3 required for AWS Secrets Manager backend") from e

    client = boto3.client("secretsmanager")
    secret_id = f"{namespace}/{key}" if namespace else key
    try:
        response = client.get_secret_value(SecretId=secret_id)
    except Exception as e:
        raise SecretBackendError(f"AWS Secrets Manager lookup failed for {secret_id}: {type(e).__name__}") from e
    return response.get("SecretString", "")


def _get_gcp(key: str, namespace: str | None) -> str:
    """Read from GCP Secret Manager via Workload Identity (D-18)."""
    try:
        from google.cloud import secretmanager
    except ImportError as e:
        raise SecretBackendError("google-cloud-secret-manager required for GCP backend") from e

    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        raise SecretBackendError("GCP_PROJECT_ID env var not set")

    secret_name = f"projects/{project}/secrets/{namespace + '-' + key if namespace else key}/versions/latest"
    client = secretmanager.SecretManagerServiceClient()
    try:
        response = client.access_secret_version(request={"name": secret_name})
    except Exception as e:
        raise SecretBackendError(f"GCP Secret Manager lookup failed for {secret_name}: {type(e).__name__}") from e
    return response.payload.data.decode("utf-8")


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════


def get_secret(
    key: str,
    namespace: str | None = None,
    *,
    default: Any = ...,
) -> str:
    """Resolve a secret by key, based on the current environment.

    Args:
        key: Secret name (e.g., 'DB_PASSWORD', 'EXTERNAL_API_KEY').
        namespace: Optional scope (e.g., service name). Used in secret ID construction.
        default: If provided, return this on miss. If ..., raise SecretNotFoundError.

    Returns:
        The secret value as a string.

    Raises:
        SecretNotFoundError: Secret not present in the configured backend (no default).
        SecretBackendError: Backend is misconfigured or unreachable.

    Invariants:
        - Never logs the secret value (D-17)
        - Never falls through to os.environ in staging/production (D-18)
    """
    env = _detect_environment()
    try:
        if env == "local":
            value = _get_local(key)
        elif env == "ci":
            value = _get_ci(key)
        elif env in {"staging", "production"}:
            cloud = _detect_cloud()
            if cloud == "aws":
                value = _get_aws(key, namespace)
            elif cloud == "gcp":
                value = _get_gcp(key, namespace)
            else:
                raise SecretBackendError(
                    f"In {env} but CLOUD_PROVIDER not detected. Set CLOUD_PROVIDER=aws|gcp. "
                    "os.environ fallback is disabled in non-local/non-CI environments (D-18)."
                )
        else:
            raise SecretBackendError(f"Unknown environment: {env!r}")
    except SecretNotFoundError:
        if default is not ...:
            return default
        raise

    # NEVER log the value. Only log resolution success with redaction.
    logger.debug("Secret resolved", extra={"key": key, "namespace": namespace, "env": env})
    return value


def require_secret(key: str, namespace: str | None = None) -> str:
    """Strict variant: raises SecretNotFoundError on miss; no default allowed.

    Use this for secrets that MUST exist in prod (DB credentials, API keys).
    """
    return get_secret(key, namespace=namespace)


__all__ = [
    "get_secret",
    "require_secret",
    "SecretNotFoundError",
    "SecretBackendError",
]
