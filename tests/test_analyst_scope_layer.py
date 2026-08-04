"""Analyst scope layer — hermetic, no network calls."""
from atlys_agentic import paths


def test_cuj2_simple_exists_and_is_reasonably_sized():
    doc = paths.REPO_ROOT / "docs" / "CUJ2-simple.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert len(text) > 200
    assert len(text.encode("utf-8")) < 10_000  # embedding ceiling: short enough to embed on every call
