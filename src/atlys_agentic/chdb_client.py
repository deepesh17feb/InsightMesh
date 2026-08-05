import json
import re
import sqlite3
import threading

from atlys_agentic import paths

_chdb_lock = threading.Lock()
_chdb_session = None


def _get_chdb_session():
    global _chdb_session
    if _chdb_session is None:
        try:
            import chdb.session
            paths.CHDB_PATH.mkdir(parents=True, exist_ok=True)
            _chdb_session = chdb.session.Session(str(paths.CHDB_PATH))
        except Exception:
            _chdb_session = None
    return _chdb_session

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
        "table" String,
        ddl String,
        columns_json String,
        spec_id String,
        version UInt16,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY ("table", version)
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
        finding_key String,
        spec_id String,
        question String,
        answer_md String,
        confidence Float32,
        cuts_json String,
        trace_id String,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY (finding_key, spec_id, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS table_semantics (
        table_name String,
        spec_id String,
        description String,
        concepts String,
        embedding Array(Float32),
        version UInt16,
        created_at DateTime
    ) ENGINE = MergeTree ORDER BY (table_name, version)
    """,
]


def _sqlite_cosine_distance(a_val, b_val):
    if not a_val or not b_val:
        return 1.0
    import math
    if isinstance(a_val, str):
        try:
            a_val = json.loads(a_val)
        except Exception:
            return 1.0
    if isinstance(b_val, str):
        try:
            b_val = json.loads(b_val)
        except Exception:
            return 1.0
    if not isinstance(a_val, (list, tuple)) or not isinstance(b_val, (list, tuple)):
        return 1.0
    if len(a_val) != len(b_val) or len(a_val) == 0:
        return 1.0
    dot = sum(float(x) * float(y) for x, y in zip(a_val, b_val))
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a_val))
    norm_b = math.sqrt(sum(float(y) * float(y) for y in b_val))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return max(0.0, min(2.0, 1.0 - (dot / (norm_a * norm_b))))


def _ch_types_to_sqlite(sql: str) -> str:
    """Rewrite a ClickHouse CREATE TABLE into something SQLite will accept."""
    sql = re.sub(r"\)\s*ENGINE\s*=.*$", ")", sql, flags=re.DOTALL | re.IGNORECASE)
    for pattern, repl in (
        (r"\bUInt\d+\b", "INTEGER"),
        (r"\bInt\d+\b", "INTEGER"),
        (r"\bFloat\d+\b", "REAL"),
        (r"\bDateTime\b", "TEXT"),
        (r"\bString\b", "TEXT"),
        (r"\bLowCardinality\([^)]+\)", "TEXT"),
        (r"\bNullable\([^)]+\)", "TEXT"),
        (r"\bArray\([^)]+\)", "TEXT"),
        (r"\bUUID\b", "TEXT"),
        (r"\btable\s+TEXT\b", '"table" TEXT'),
    ):
        sql = re.sub(pattern, repl, sql, flags=re.IGNORECASE)
    return sql


def _get_sqlite_conn():
    paths.CHDB_PATH.mkdir(parents=True, exist_ok=True)
    db_file = paths.CHDB_PATH / "metadata.sqlite"
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("cosineDistance", 2, _sqlite_cosine_distance)
    conn.create_function("cosinedistance", 2, _sqlite_cosine_distance)
    with conn:
        cursor = conn.cursor()
        for ddl in _SCHEMA_DDL:
            try:
                cursor.execute(_ch_types_to_sqlite(ddl))
            except Exception:
                pass
        # Ensure finding_key column is present if insights table already existed
        try:
            cursor.execute("SELECT finding_key FROM insights LIMIT 1")
        except Exception:
            try:
                cursor.execute("ALTER TABLE insights ADD COLUMN finding_key TEXT DEFAULT ''")
            except Exception:
                pass
    return conn


def _run_sqlite_fallback(sql: str, fmt: str = "JSON"):
    conn = _get_sqlite_conn()
    clean = sql
    if clean.strip().upper() == "SHOW TABLES":
        clean = "SELECT name, name AS table_name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    elif clean.strip().upper().startswith("CREATE TABLE"):
        clean = _ch_types_to_sqlite(clean)

    clean = re.sub(r"^\s*TRUNCATE\s+TABLE\s+(\w+)", r"DELETE FROM \1", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bnow\(\)", "datetime('now')", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bcount\(\)", "count(*)", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^\s*INSERT\s+INTO\s+business_context\s+VALUES\s*\(\s*'", "INSERT INTO business_context (section, key, definition, version, valid_from) VALUES ('", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bWHERE\s+table\b", 'WHERE "table"', clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bWHERE\s+table_name\b", 'WHERE "table"', clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bOR\s+table_name\b", 'OR "table"', clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bSELECT\s+table\b", 'SELECT "table"', clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bORDER\s+BY\s+table\b", 'ORDER BY "table"', clean, flags=re.IGNORECASE)
    # Convert unquoted float array literal e.g. [0.123, -0.456] into string '[0.123, -0.456]'
    clean = re.sub(r"(?<!['\"\w])\[\s*(-?\d+\.?\d*(?:\s*,\s*-?\d+\.?\d*)*)\s*\](?!['\"\w])", r"'[\1]'", clean)

    with conn:
        cursor = conn.cursor()
        cursor.execute(clean)
        if cursor.description:
            cols = [col[0] for col in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
            return rows
        return []


def run(sql: str, fmt: str = "JSON"):
    try:
        with _chdb_lock:
            session = _get_chdb_session()
            result = session.query(sql, fmt)
        text = str(result)
        if fmt == "JSON" and text.strip():
            payload = json.loads(text)
            return payload.get("data", [])
        return text
    except Exception:
        return _run_sqlite_fallback(sql, fmt=fmt)


def init_schema() -> None:
    for ddl in _SCHEMA_DDL:
        run(ddl, fmt="CSV")


def init_base_context() -> int:
    """Chunk base_context.md into business_context rows, one row per
    numbered section (## N. Title) split further by list item / paragraph."""
    init_schema()
    try:
        run("TRUNCATE TABLE business_context", fmt="CSV")
    except Exception:
        pass
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
