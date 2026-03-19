"""
Langfuse observability — thin wrapper for tracing and LLM call logging.

Isolates all Langfuse SDK imports so the rest of the codebase never touches
langfuse directly.  Every function degrades gracefully to a no-op when
Langfuse env vars are absent or the package is not installed.

Two integration layers:

Layer 1 (automatic):
    ``init_observability()`` registers Langfuse as a LiteLLM success/failure
    callback.  Every ``litellm.completion()`` call is then auto-logged with
    token counts, latency, cost, model, and raw inputs/outputs.

Layer 2 (explicit trace hierarchy):
    ``create_trace`` / ``create_span`` / ``end_span`` let the AgentLoop build
    a structured trace tree: Trace(agent_turn) → Span(planner) → Generation.
    ``llm_metadata`` produces the dict that LiteLLM needs to nest its
    auto-logged generations under the correct span.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_langfuse_client: Any = None


def langfuse_enabled() -> bool:
    """Return True if Langfuse credentials are configured."""
    from chatshop.config import settings

    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def init_observability() -> None:
    """Register Langfuse as a LiteLLM callback if credentials are present.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _langfuse_client

    if not langfuse_enabled() or _langfuse_client is not None:
        return

    try:
        import litellm
        from langfuse import Langfuse

        from chatshop.config import settings

        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        print(f"[observability] Langfuse client initialised: {_langfuse_client is not None}")
    except Exception as exc:
        print(f"[observability] Langfuse init FAILED: {exc}")
        logger.warning("Langfuse init failed", exc_info=True)


def create_trace(
    name: str,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None,
) -> Any:
    """Create a Langfuse trace and return the trace object (or None)."""
    if _langfuse_client is None:
        print("[observability] create_trace skipped — client is None")
        return None
    try:
        kwargs: dict[str, Any] = {"name": name}
        if session_id:
            kwargs["session_id"] = session_id
        if user_id:
            kwargs["user_id"] = user_id
        if metadata:
            kwargs["metadata"] = metadata
        trace = _langfuse_client.trace(**kwargs)
        print(f"[observability] Trace created: id={trace.id}, trace_id={trace.trace_id}")
        return trace
    except Exception as exc:
        print(f"[observability] create_trace FAILED: {exc}")
        return None


def create_span(
    trace: Any,
    name: str,
    input: dict | None = None,
) -> Any:
    """Create a span under the given trace.  Returns the span object or None."""
    if trace is None:
        return None
    try:
        kwargs: dict[str, Any] = {"name": name}
        if input is not None:
            kwargs["input"] = input
        return trace.span(**kwargs)
    except Exception:
        logger.debug("Failed to create Langfuse span", exc_info=True)
        return None


def end_span(span: Any, output: dict | None = None) -> None:
    """End a span with optional output metadata.  No-op if span is None."""
    if span is None:
        return
    try:
        kwargs: dict[str, Any] = {}
        if output is not None:
            kwargs["output"] = output
        span.end(**kwargs)
    except Exception:
        logger.debug("Failed to end Langfuse span", exc_info=True)


def llm_metadata(
    trace: Any,
    generation_name: str | None = None,
) -> dict | None:
    """Build the metadata dict that LiteLLM uses to attach a generation to our trace.

    Args:
        trace: The Langfuse trace object from ``create_trace``.
        generation_name: Label for this generation in the Langfuse dashboard
            (e.g. ``"planner"``, ``"evaluator"``).

    Returns None when tracing is disabled so callers can skip it cleanly.
    """
    if trace is None:
        return None
    try:
        meta: dict[str, str] = {"existing_trace_id": trace.id}
        if generation_name:
            meta["generation_name"] = generation_name
        print(f"[observability] llm_metadata: {meta}")
        return meta
    except Exception as exc:
        print(f"[observability] llm_metadata FAILED: {exc}")
        return None


def flush_observability() -> None:
    """Flush any pending Langfuse events.  Safe to call when disabled."""
    if _langfuse_client is None:
        return
    try:
        _langfuse_client.flush()
    except Exception:
        logger.debug("Langfuse flush failed", exc_info=True)
