"""Stable error envelope for FastAPI services (Phase 1.2).

Goal: every non-2xx response (4xx and 5xx) returns the **same JSON shape**
regardless of which handler raised it. Clients can rely on the contract
without inspecting endpoint-specific schemas, and operators can grep for
``error.code`` in logs to triage incidents.

## Envelope shape

```json
{
  "error": {
    "code": "MODEL_NOT_LOADED",
    "message": "Model artefact not loaded; readiness probe should have caught this.",
    "request_id": "8f2a1c4e6b7d-...",
    "trace_id": null,
    "details": {}
  }
}
```

* ``code`` — stable, screaming-snake-case identifier. Add new values to
  :class:`ErrorCode`; never reword an existing one (clients alert on it).
* ``message`` — human-readable; safe for end-users (no stack traces, no PII).
* ``request_id`` — UUID4 set by ``RequestIDMiddleware`` (``X-Request-ID``).
* ``trace_id`` — populated when OTel tracing is enabled; ``None`` otherwise.
* ``details`` — optional structured field for machine-readable context
  (e.g. Pandera failure cases, validation field names). Always present
  but may be empty.

## Why not FastAPI's default ``detail`` shape?

FastAPI emits ``{"detail": "..."}`` for ``HTTPException`` and a different
shape (``{"detail": [{"loc": [...], "msg": "...", "type": "..."}, ...]}``)
for Pydantic validation. Two shapes per service multiply by N services
into a real client-side mess. The envelope here flattens both into one
contract while preserving the original validation cases under ``details``.

## Backwards compatibility

The middleware is opt-in via ``ERROR_ENVELOPE_ENABLED`` (default ``true``).
Set it to ``false`` to keep the FastAPI default shape — useful only for
gradual migration of consumers; do not leave it disabled in prod.
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"


class ErrorCode(str, Enum):
    """Stable error codes. Append-only — never rename or remove a value
    once it has shipped, because clients alert on these strings.
    """

    # 4xx — client errors
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    UNPROCESSABLE_ENTITY = "UNPROCESSABLE_ENTITY"
    RATE_LIMITED = "RATE_LIMITED"

    # 5xx — server errors
    MODEL_NOT_LOADED = "MODEL_NOT_LOADED"
    MODEL_RELOAD_FAILED = "MODEL_RELOAD_FAILED"
    INTERNAL_PREDICTION_ERROR = "INTERNAL_PREDICTION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


def _build_envelope(
    code: str,
    message: str,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Construct the canonical error envelope dict."""
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "trace_id": trace_id,
            "details": details or {},
        }
    }


def make_error_response(
    *,
    status_code: int,
    code: ErrorCode | str,
    message: str,
    request: Optional[Request] = None,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    """Build a :class:`JSONResponse` carrying the error envelope.

    The handler reads ``request.state.request_id`` if the
    :class:`RequestIDMiddleware` already set it, otherwise the
    ``request_id`` field is ``None`` (still present for shape stability).
    """
    code_str = code.value if isinstance(code, ErrorCode) else code
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    trace_id = getattr(getattr(request, "state", None), "trace_id", None)
    body = _build_envelope(
        code=code_str,
        message=message,
        request_id=request_id,
        trace_id=trace_id,
        details=details,
    )
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


class ServiceError(Exception):
    """Application-level error that maps cleanly to the envelope.

    Prefer raising :class:`ServiceError` over :class:`HTTPException` in
    new code; the global handler converts it to the envelope without
    additional plumbing in each route.
    """

    def __init__(
        self,
        *,
        code: ErrorCode | str,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


# ---------------------------------------------------------------------------
# Middleware: request_id
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Read or generate a per-request correlation id.

    Behaviour:
    - Honours an inbound ``X-Request-ID`` header if it is a non-empty,
      reasonable-length string (<=128 chars). Otherwise a UUID4 is
      generated.
    - Stores the id on ``request.state.request_id`` for handler access.
    - Echoes it back in the response ``X-Request-ID`` header so clients
      can correlate even when the body has not been parsed (e.g. on
      error).
    - If a ``X-Trace-ID`` header is present, it is forwarded to
      ``request.state.trace_id`` (read-only — the middleware does NOT
      generate a trace id; that is the OTel SDK's job).
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming if incoming and len(incoming) <= 128 else uuid.uuid4().hex
        request.state.request_id = request_id
        trace_in = request.headers.get(TRACE_ID_HEADER, "").strip()
        if trace_in and len(trace_in) <= 128:
            request.state.trace_id = trace_in
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        if getattr(request.state, "trace_id", None):
            response.headers[TRACE_ID_HEADER] = request.state.trace_id
        return response


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Map :class:`ServiceError` to the envelope."""
    return make_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request=request,
        details=exc.details,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Map :class:`HTTPException` (FastAPI/starlette) to the envelope.

    Bridges existing handlers (``raise HTTPException(...)``) into the new
    envelope without rewriting every route. The mapping uses the status
    code to pick a sensible :class:`ErrorCode`; if ``exc.detail`` is
    already a dict, its contents go into ``details``.
    """
    code = _status_to_error_code(exc.status_code)
    if isinstance(exc.detail, dict):
        message = str(exc.detail.get("message") or exc.detail.get("detail") or code.value)
        details = exc.detail
    else:
        message = str(exc.detail) if exc.detail else code.value
        details = None
    response = make_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        request=request,
        details=details,
    )
    # Preserve security-relevant headers like WWW-Authenticate.
    if exc.headers:
        for k, v in exc.headers.items():
            response.headers.setdefault(k, v)
    return response


async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Map Pydantic validation errors to the envelope.

    Original errors are preserved verbatim under ``details.validation`` so
    clients that want field-level diagnostics still have them.
    """
    return make_error_response(
        status_code=422,
        code=ErrorCode.SCHEMA_VALIDATION_FAILED,
        message="Request payload failed schema validation.",
        request=request,
        details={"validation": exc.errors()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler. Logs the trace; emits a generic envelope.

    Never leaks the exception class name or message to the client to
    avoid information disclosure (D-32). Operators correlate via
    ``request_id`` in the structured log line.
    """
    logger.exception("Unhandled exception", extra={"request_id": getattr(request.state, "request_id", None)})
    return make_error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred. Operators have been notified.",
        request=request,
    )


def _status_to_error_code(status_code: int) -> ErrorCode:
    mapping = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        413: ErrorCode.PAYLOAD_TOO_LARGE,
        415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        422: ErrorCode.UNPROCESSABLE_ENTITY,
        429: ErrorCode.RATE_LIMITED,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }
    if status_code in mapping:
        return mapping[status_code]
    return ErrorCode.INTERNAL_ERROR if status_code >= 500 else ErrorCode.UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Public install hook
# ---------------------------------------------------------------------------
def install_error_envelope(app: FastAPI) -> None:
    """Wire the middleware + exception handlers into a FastAPI app.

    Idempotent — calling twice does not register duplicate handlers.
    Apps may opt out by setting ``ERROR_ENVELOPE_ENABLED=false``.
    """
    import os

    if os.getenv("ERROR_ENVELOPE_ENABLED", "true").lower() == "false":
        logger.info("ERROR_ENVELOPE_ENABLED=false — keeping FastAPI default error shape.")
        return

    # Avoid double-install on hot reload.
    if getattr(app.state, "_error_envelope_installed", False):
        return

    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.state._error_envelope_installed = True
    logger.info("Error envelope installed (middleware + handlers).")


__all__ = [
    "ErrorCode",
    "ServiceError",
    "RequestIDMiddleware",
    "REQUEST_ID_HEADER",
    "TRACE_ID_HEADER",
    "install_error_envelope",
    "make_error_response",
    "service_error_handler",
    "http_exception_handler",
    "request_validation_exception_handler",
    "unhandled_exception_handler",
]
