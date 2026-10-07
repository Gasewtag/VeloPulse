"""Observability context variables for distributed tracing and correlation."""

import uuid
from contextvars import ContextVar, Token

_correlation_id_ctx_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Retrieve current correlation ID from context, or empty string if not set."""
    return _correlation_id_ctx_var.get()


def set_correlation_id(correlation_id: str | None = None) -> Token[str]:
    """Set correlation ID in context. Generates new UUID4 if not provided."""
    cid = correlation_id.strip() if correlation_id and correlation_id.strip() else str(uuid.uuid4())
    return _correlation_id_ctx_var.set(cid)


def reset_correlation_id(token: Token[str]) -> None:
    """Reset correlation ID back to previous state."""
    _correlation_id_ctx_var.reset(token)
