"""Langfuse tracing helpers.

Uses the Langfuse v4 (OTEL-based) SDK: `get_client()` returns a process-wide
singleton configured from LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST env vars, and
`start_as_current_observation(...)` is a context manager — nesting one inside
another builds the trace tree automatically via OTEL context propagation, so
callers never pass a trace_id by hand.
"""
from contextlib import contextmanager

from dotenv import load_dotenv
from langfuse import get_client

from atlys_agentic import paths

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")


def init_litellm_callbacks() -> None:
    """No-op: litellm's built-in "langfuse" success_callback targets the
    Langfuse v2 SDK's module layout (langfuse.version) and crashes against
    the installed v4 (OTEL-based) SDK — confirmed by running it. Every
    agent step, tool call, and result is already traced explicitly via
    trace()/step() below, which is the primary mechanism, not a supplement,
    so no per-LLM-call auto-tracing is lost in a way that matters here."""
    return


def client():
    return get_client()


_current_trace_id: str | None = None


@contextmanager
def trace(name: str, input: dict | None = None, metadata: dict | None = None):
    """Root span for one pipeline run (one ingestion, one analysis question).
    Everything nested inside via step() becomes part of the same trace."""
    global _current_trace_id
    with client().start_as_current_observation(
        name=name, as_type="span", input=input or {}, metadata=metadata or {}
    ) as span:
        # captured while the span is active — get_trace_url() needs this
        # explicitly once the caller wants the URL after the block exits.
        _current_trace_id = client().get_current_trace_id()
        yield span
    client().flush()


@contextmanager
def step(name: str, input: dict | None = None, metadata: dict | None = None):
    """One agent step / tool call / SQL statement / context source, nested
    under whichever trace() is currently active. Call `span.update(output=...)`
    inside the block once the result is known."""
    with client().start_as_current_observation(
        name=name, as_type="span", input=input or {}, metadata=metadata or {}
    ) as span:
        yield span


def trace_url() -> str | None:
    """Safe to call after the trace() block has exited — uses the trace_id
    captured while the span was active, since get_trace_url() with no
    explicit trace_id only works inside an active span context."""
    if _current_trace_id is None:
        return None
    try:
        return client().get_trace_url(trace_id=_current_trace_id)
    except Exception:
        return None


def new_trace(spec_id: str) -> str:
    """Create a new trace id tagged with spec_id."""
    global _current_trace_id
    try:
        c = client()
        if hasattr(c, "trace"):
            t = c.trace(name=f"clickathon-run-{spec_id}", tags=[spec_id])
            _current_trace_id = getattr(t, "id", str(t))
            return _current_trace_id
    except Exception:
        pass
    _current_trace_id = f"trace-{spec_id}"
    return _current_trace_id


def span(trace_id: str, name: str, input: dict, output: dict, metadata: dict | None = None) -> None:
    """Record a span with input/output under the trace."""
    try:
        c = client()
        if hasattr(c, "span"):
            c.span(trace_id=trace_id, name=name, input=input, output=output, metadata=metadata or {})
        elif hasattr(c, "start_as_current_observation"):
            with c.start_as_current_observation(name=name, as_type="span", input=input, metadata=metadata or {}) as s:
                if hasattr(s, "update"):
                    s.update(output=output)
    except Exception:
        pass

