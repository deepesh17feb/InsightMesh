import json
import re

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


import sqlite3

def _get_sqlite_conn():
    paths.CHDB_PATH.mkdir(parents=True, exist_ok=True)
    db_file = paths.CHDB_PATH / "metadata.sqlite"
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        cursor = conn.cursor()
        for ddl in _SCHEMA_DDL:
            clean = re.sub(r"\)\s*ENGINE\s*=.*$", ")", ddl, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"\bUInt\d+\b", "INTEGER", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bInt\d+\b", "INTEGER", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bFloat\d+\b", "REAL", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bDateTime\b", "TEXT", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bString\b", "TEXT", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bLowCardinality\([^)]+\)", "TEXT", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bNullable\([^)]+\)", "TEXT", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\bUUID\b", "TEXT", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\btable\s+TEXT\b", '"table" TEXT', clean, flags=re.IGNORECASE)
            try:
                cursor.execute(clean)
            except Exception:
                pass
    return conn


def _run_sqlite_fallback(sql: str, fmt: str = "JSON"):
    conn = _get_sqlite_conn()
    clean = sql
    if clean.strip().upper() == "SHOW TABLES":
        clean = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    elif clean.strip().upper().startswith("CREATE TABLE"):
        clean = re.sub(r"\)\s*ENGINE\s*=.*$", ")", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"\bUInt\d+\b", "INTEGER", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bInt\d+\b", "INTEGER", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bFloat\d+\b", "REAL", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bDateTime\b", "TEXT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bString\b", "TEXT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bLowCardinality\([^)]+\)", "TEXT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bNullable\([^)]+\)", "TEXT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bUUID\b", "TEXT", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\btable\s+TEXT\b", '"table" TEXT', clean, flags=re.IGNORECASE)

    clean = re.sub(r"\bnow\(\)", "datetime('now')", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bcount\(\)", "count(*)", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bWHERE\s+table\b", 'WHERE "table"', clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bSELECT\s+table\b", 'SELECT "table"', clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bORDER\s+BY\s+table\b", 'ORDER BY "table"', clean, flags=re.IGNORECASE)

    with conn:
        cursor = conn.cursor()
        cursor.execute(clean)
        if cursor.description:
            cols = [col[0] for col in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
            return rows
        return []


def run(sql: str, fmt: str = "JSON"):
    paths.CHDB_PATH.mkdir(parents=True, exist_ok=True)
    try:
        import chdb
        result = chdb.query(sql, output_format=fmt, path=str(paths.CHDB_PATH))
        text = str(result)
        if fmt == "JSON" and text.strip():
            payload = json.loads(text)
            return payload.get("data", [])
        return text
    except (ImportError, Exception):
        return _run_sqlite_fallback(sql, fmt=fmt)


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
