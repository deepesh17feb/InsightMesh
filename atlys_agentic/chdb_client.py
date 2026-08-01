import json
import re

import chdb

from atlys_agentic import paths

_SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS business_context (
        id UInt32,
        section String,
        key String,
        definition String,
        version UInt16,
        valid_from DateTime,
        source String,
        status String
    ) ENGINE = MergeTree ORDER BY (section, key, version)
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_registry (
        table String,
        ddl String,
        columns_json String,
        spec_id String,
        version UInt16,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY (table, version)
    """,
    """
    CREATE TABLE IF NOT EXISTS context_changelog (
        ts DateTime,
        change_type String,
        before String,
        after String,
        agent String,
        trace_id String
    ) ENGINE = MergeTree ORDER BY ts
    """,
    """
    CREATE TABLE IF NOT EXISTS insights (
        spec_id String,
        question String,
        answer_md String,
        confidence Float32,
        cuts_json String,
        trace_id String,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY (spec_id, created_at)
    """,
]


def run(sql: str, fmt: str = "JSON"):
    paths.CHDB_PATH.mkdir(parents=True, exist_ok=True)
    result = chdb.query(sql, output_format=fmt, path=str(paths.CHDB_PATH))
    text = str(result)
    if fmt == "JSON" and text.strip():
        payload = json.loads(text)
        return payload.get("data", [])
    return text


def init_schema() -> None:
    for ddl in _SCHEMA_DDL:
        run(ddl, fmt="CSV")


def init_base_context() -> int:
    """Chunk base_context.md into business_context rows, one row per
    numbered section (## N. Title) split further by list item / paragraph."""
    text = paths.BASE_CONTEXT_MD.read_text(encoding="utf-8")
    sections = re.split(r"\n## ", text)[1:]  # drop preamble before first "## "
    inserted = 0
    next_id = 1
    for section in sections:
        lines = section.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        for i, chunk in enumerate([p for p in body.split("\n\n") if p.strip()]):
            key = f"{title[:40]}#{i}".replace("'", "").replace("\n", " ")
            definition = chunk.replace("'", "''")
            run(
                f"""INSERT INTO business_context VALUES
                ({next_id}, '{title.replace("'", "''")}', '{key}',
                 '{definition}', 1, now(), 'base_context.md', 'active')""",
                fmt="CSV",
            )
            next_id += 1
            inserted += 1
    return inserted
