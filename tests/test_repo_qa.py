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


from atlys_agentic import tools_repo


def test_search_repo_returns_snippets_not_whole_chunks():
    hits = tools_repo.search_repo("how do I run the backend", k=3)
    assert hits
    assert set(hits[0]) == {"path", "heading", "start_line", "score", "snippet"}
    assert len(hits[0]["snippet"]) <= tools_repo.SNIPPET_CHARS


def test_read_repo_file_reads_a_tracked_file():
    text = tools_repo.read_repo_file("README.md", start=0, end=5)
    assert "Error:" not in text
    assert len(text.splitlines()) <= 5


def test_read_repo_file_caps_the_line_span():
    text = tools_repo.read_repo_file("README.md", start=0, end=99999)
    assert len(text.splitlines()) <= tools_repo.MAX_LINES


def test_read_repo_file_rejects_parent_traversal():
    assert tools_repo.read_repo_file("../../etc/passwd").startswith("Error:")
    assert tools_repo.read_repo_file("docs/../../../etc/passwd").startswith("Error:")


def test_read_repo_file_rejects_absolute_paths_outside_the_repo():
    assert tools_repo.read_repo_file("/etc/passwd").startswith("Error:")


def test_read_repo_file_rejects_a_symlink_escaping_the_repo(tmp_path):
    from atlys_agentic import paths
    link = paths.REPO_ROOT / "_test_escape_link"
    link.symlink_to("/etc/passwd")
    try:
        assert tools_repo.read_repo_file("_test_escape_link").startswith("Error:")
    finally:
        link.unlink()


def test_read_repo_file_reports_a_missing_file_without_raising():
    assert tools_repo.read_repo_file("no/such/file.md").startswith("Error:")


def test_read_repo_file_negative_end_is_clamped():
    """Negative end must not bypass MAX_LINES via Python's end-relative slice.

    Regression test for: end=-1 used to return lines[0:-1], which is almost the
    entire file, bypassing the MAX_LINES cap.
    """
    text = tools_repo.read_repo_file("src/atlys_agentic/specs/06_unseen/events.ndjson", start=0, end=-1)
    assert len(text.splitlines()) <= tools_repo.MAX_LINES


def test_read_repo_file_inverted_span_is_bounded():
    """start > end should return bounded or empty output, never the whole file."""
    text = tools_repo.read_repo_file("README.md", start=50, end=10)
    assert len(text.splitlines()) <= tools_repo.MAX_LINES


def test_read_repo_file_rejects_non_string_path():
    """Non-string path should return an error string, not raise."""
    result = tools_repo.read_repo_file(5)
    assert result.startswith("Error:")


def test_read_repo_file_rejects_non_integer_start():
    """Non-integer start should return an error string, not raise."""
    result = tools_repo.read_repo_file("README.md", start="abc")
    assert result.startswith("Error:")


def test_read_repo_file_rejects_non_integer_end():
    """Non-integer end should return an error string, not raise."""
    result = tools_repo.read_repo_file("README.md", end=None)
    assert result.startswith("Error:")


def test_read_repo_file_rejects_none_path():
    """None path should return an error string, not raise."""
    result = tools_repo.read_repo_file(None)
    assert result.startswith("Error:")
