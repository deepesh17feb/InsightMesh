"""Langfuse tracing helpers.

Uses the Langfuse v4 (OTEL-based) SDK: `get_client()` returns a process-wide
singleton configured from LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST env vars, and
`start_as_current_observation(...)` is a context manager — nesting one inside
another builds the trace tree automatically via OTEL context propagation, so
callers never pass a trace_id by hand.
"""
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from langfuse import Langfuse

from atlys_agentic import paths

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env")
load_dotenv(paths.REPO_ROOT / ".env")

_client = None


def resolve_run_mode(run_mode: str | None = None) -> str:
    """Resolve active execution mode: 'test_run', 'dry_run', 'live_run', or 'librechat_client'."""
    if run_mode in ("test_run", "live_run", "dry_run", "librechat_client", "librechat"):
        return "librechat_client" if run_mode in ("librechat_client", "librechat") else run_mode
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "test_run"
    return "live_run"


def format_span_name(name: str, run_mode: str | None = None) -> str:
    """Format span name with run mode prefix: e.g. 'live_run::infer_schema', 'dry_run::audit', 'librechat_client::chat_completions'."""
    mode = resolve_run_mode(run_mode)
    if name.startswith((
        "test_run::",
        "live_run::",
        "dry_run::",
        "librechat_client::",
        "librechat::",
        "[TEST_RUN]",
        "[LIVE_RUN]",
        "[DRY_RUN]",
        "[LIBRECHAT]",
    )):
        return name
    return f"{mode}::{name}"


def client() -> Langfuse:
    """Return explicit Langfuse v4 client initialized from environment."""
    global _client
    if _client is None:
        pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sk = os.environ.get("LANGFUSE_SECRET_KEY")
        host = os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
        _client = Langfuse(public_key=pk, secret_key=sk, host=host)
    return _client


def flush() -> None:
    """Flush pending observations to Langfuse Cloud."""
    try:
        c = client()
        c.flush()
    except Exception:
        pass


_current_trace_id: str | None = None
_current_trace_url: str | None = None


@contextmanager
def trace(name: str, input: dict | None = None, metadata: dict | None = None, run_mode: str | None = None):
    """Root span for one pipeline run (one ingestion, one analysis question).
    Everything nested inside via step() becomes part of the same trace."""
    global _current_trace_id, _current_trace_url
    mode = resolve_run_mode(run_mode)
    formatted_name = format_span_name(name, mode)
    meta = (metadata or {}).copy()
    meta["run_mode"] = mode

    c = client()
    with c.start_as_current_observation(
        name=formatted_name, as_type="span", input=input or {}, metadata=meta
    ) as span:
        _current_trace_id = c.get_current_trace_id()
        _current_trace_url = c.get_trace_url(trace_id=_current_trace_id) if _current_trace_id else None
        yield span
    c.flush()


@contextmanager
def step(name: str, input: dict | None = None, metadata: dict | None = None, run_mode: str | None = None):
    """One agent step / tool call / SQL statement / context source, nested
    under whichever trace() is currently active. Call `span.update(output=...)`
    inside the block once the result is known."""
    mode = resolve_run_mode(run_mode)
    formatted_name = format_span_name(name, mode)
    meta = (metadata or {}).copy()
    meta["run_mode"] = mode

    c = client()
    with c.start_as_current_observation(
        name=formatted_name, as_type="span", input=input or {}, metadata=meta
    ) as span:
        yield span


def generation(
    name: str,
    model: str,
    input: dict | list | str,
    output: str | dict,
    usage_details: dict | None = None,
    metadata: dict | None = None,
    run_mode: str | None = None,
) -> None:
    """Record an LLM generation observation in Langfuse."""
    mode = resolve_run_mode(run_mode)
    formatted_name = format_span_name(name, mode)
    meta = (metadata or {}).copy()
    meta["run_mode"] = mode

    try:
        c = client()
        with c.start_as_current_observation(
            name=formatted_name,
            as_type="generation",
            input=input,
            model=model,
            metadata=meta,
        ) as gen:
            gen.update(output=output, usage_details=usage_details or {})
    except Exception:
        pass


def trace_url() -> str | None:
    """Safe to call after the trace() block has exited — returns the captured trace URL."""
    global _current_trace_url, _current_trace_id
    if _current_trace_id is None:
        return None
    if _current_trace_url:
        return _current_trace_url
    try:
        return client().get_trace_url(trace_id=_current_trace_id)
    except Exception:
        return None


def new_trace(spec_id: str, run_mode: str | None = None) -> str:
    """Create a new trace id tagged with spec_id and run_mode (test_run | live_run | dry_run)."""
    global _current_trace_id, _current_trace_url
    mode = resolve_run_mode(run_mode)
    trace_name = f"clickathon-{mode}-{spec_id}"
    try:
        c = client()
        if hasattr(c, "trace"):
            t = c.trace(name=trace_name, tags=[spec_id, mode])
            _current_trace_id = getattr(t, "id", str(t))
            _current_trace_url = c.get_trace_url(trace_id=_current_trace_id)
            return _current_trace_id
    except Exception:
        pass
    _current_trace_id = f"trace-{mode}-{spec_id}"
    return _current_trace_id


def span(
    trace_id: str,
    name: str,
    input: dict,
    output: dict,
    metadata: dict | None = None,
    run_mode: str | None = None,
) -> None:
    """Record a span with input/output under the trace, prefixed by run mode."""
    mode = resolve_run_mode(run_mode)
    formatted_name = format_span_name(name, mode)
    meta = (metadata or {}).copy()
    meta["run_mode"] = mode

    try:
        c = client()
        if hasattr(c, "span"):
            c.span(trace_id=trace_id, name=formatted_name, input=input, output=output, metadata=meta)
        else:
            with c.start_as_current_observation(name=formatted_name, as_type="span", input=input, metadata=meta) as s:
                if hasattr(s, "update"):
                    s.update(output=output)
    except Exception:
        pass

