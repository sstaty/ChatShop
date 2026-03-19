"""
Langfuse observability — thin wrapper for tracing and LLM generation logging.

Isolates all Langfuse SDK imports so the rest of the codebase never touches
langfuse directly.  Every function degrades gracefully to a no-op when
Langfuse env vars are absent or the package is not installed.

Trace hierarchy:
    ``create_trace`` / ``create_span`` / ``end_span`` let the AgentLoop build
    a structured trace tree.  ``log_generation`` records individual LLM calls
    nested under their parent span (not the top-level trace) with token counts,
    latency, model, and full I/O.

    Trace(agent_turn)
    ├── Span(planner)
    │   └── Generation(planner)
    ├── Span(hybrid_search)
    ├── Span(evaluator)
    │   └── Generation(evaluator)
    └── Span(conversationist)
        └── Generation(conversationist-synthesize)
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
    """Initialise the Langfuse client if credentials are present.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _langfuse_client

    if not langfuse_enabled() or _langfuse_client is not None:
        return

    try:
        from langfuse import Langfuse

        from chatshop.config import settings

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse observability initialised")
    except Exception:
        logger.warning("Langfuse init failed", exc_info=True)


def create_trace(
    name: str,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None,
) -> Any:
    """Create a Langfuse trace and return the trace object (or None)."""
    if _langfuse_client is None:
        return None
    try:
        kwargs: dict[str, Any] = {"name": name}
        if session_id:
            kwargs["session_id"] = session_id
        if user_id:
            kwargs["user_id"] = user_id
        if metadata:
            kwargs["metadata"] = metadata
        return _langfuse_client.trace(**kwargs)
    except Exception:
        logger.debug("Failed to create Langfuse trace", exc_info=True)
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


def log_generation(
    parent: Any,
    name: str,
    model: str,
    input: Any,
    output: str,
    usage: dict | None = None,
) -> None:
    """Log an LLM generation under a Langfuse span or trace.

    Called by ``LLMClient`` after each completion/stream finishes.

    Args:
        parent: Langfuse span or trace object to nest the generation under.
        name: Label for this generation (e.g. ``"planner"``, ``"evaluator"``).
        model: Model string used for the call.
        input: Messages sent to the LLM.
        output: Full response content.
        usage: Token counts dict with ``prompt_tokens``, ``completion_tokens``,
            ``total_tokens`` keys.
    """
    if parent is None:
        return
    try:
        kwargs: dict[str, Any] = {
            "name": name,
            "model": model,
            "input": input,
            "output": output,
        }
        if usage:
            kwargs["usage"] = usage
        parent.generation(**kwargs)
    except Exception:
        logger.debug("Failed to log Langfuse generation", exc_info=True)


def llm_metadata(
    parent: Any,
    generation_name: str | None = None,
) -> dict | None:
    """Build the metadata dict that LLMClient uses for Langfuse logging.

    Args:
        parent: The Langfuse span or trace to nest the generation under.
        generation_name: Label for this generation in the Langfuse dashboard.

    Returns None when tracing is disabled so callers can skip it cleanly.
    """
    if parent is None:
        return None
    return {
        "trace": parent,
        "generation_name": generation_name or "completion",
    }


def flush_observability() -> None:
    """Flush any pending Langfuse events.  Safe to call when disabled."""
    if _langfuse_client is None:
        return
    try:
        _langfuse_client.flush()
    except Exception:
        logger.debug("Langfuse flush failed", exc_info=True)
