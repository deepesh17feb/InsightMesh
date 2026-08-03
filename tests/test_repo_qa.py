"""Repository knowledge index, tools, and Q&A — hermetic, no network calls."""
from atlys_agentic import repo_index


def test_index_is_not_empty():
    assert len(repo_index.build_index()) > 50


def test_corpus_excludes_worktrees_data_and_our_own_planning_docs():
    for path in repo_index.tracked_files():
        assert not path.startswith(".worktrees/"), path
        assert not path.startswith("outputs/"), path
        assert not path.startswith("docs/superpowers/"), path
        assert not path.endswith(".ndjson"), path


def test_corpus_is_markdown_anywhere_plus_python_under_src_only():
    for path in repo_index.tracked_files():
        assert path.endswith((".md", ".py")), path
        if path.endswith(".py"):
            assert path.startswith("src/"), path


def test_chunks_carry_path_heading_and_start_line():
    chunk = repo_index.build_index()[0]
    assert set(chunk) == {"path", "heading", "text", "start_line"}
    assert chunk["start_line"] >= 1


def test_search_finds_the_run_guide():
    hits = repo_index.search("how do I run the backend", k=3)
    assert "RUN.md" in [h["path"] for h in hits]


def test_search_finds_the_cuj2_span_contract():
    hits = repo_index.search("langfuse tracing span contract", k=5)
    assert "docs/CUJ2.md" in [h["path"] for h in hits]


def test_search_respects_k():
    assert len(repo_index.search("clickhouse schema", k=2)) <= 2


def test_search_orders_by_descending_score():
    scores = [h["score"] for h in repo_index.search("clickhouse schema ingestion", k=10)]
    assert scores == sorted(scores, reverse=True)


def test_search_on_empty_or_stopword_only_question_returns_nothing():
    assert repo_index.search("") == []
    assert repo_index.search("the and for") == []


def test_paths_prefix_restricts_the_subtree():
    hits = repo_index.search(
        "express checkout funnel",
        k=3,
        paths_prefix=("docs/", "problem statment/specs/"),
    )
    assert hits
    for hit in hits:
        assert hit["path"].startswith(("docs/", "problem statment/specs/"))
