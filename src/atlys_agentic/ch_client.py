import os
import subprocess

import clickhouse_connect
from dotenv import load_dotenv

from atlys_agentic import paths

load_dotenv(paths.ATLYS_AGENTIC_DIR / "config" / ".env", override=True)
load_dotenv(paths.REPO_ROOT / ".env", override=True)

_client = None
_client_db = None


def get_client():
    """Cached clickhouse_connect client, rebuilt when CLICKHOUSE_DATABASE changes."""
    global _client, _client_db
    database = os.environ.get("CLICKHOUSE_DATABASE", "default")
    if _client is None or _client_db != database:
        _client = clickhouse_connect.get_client(
            host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
            port=int(os.environ.get("CLICKHOUSE_PORT", "8443")),
            username=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            secure=os.environ.get("CLICKHOUSE_SECURE", "true").lower() == "true",
            database=database,
        )
        _client_db = database
    return _client


def command(sql: str) -> None:
    get_client().command(sql)


def select(sql: str) -> list[dict]:
    result = get_client().query(sql)
    return [dict(zip(result.column_names, row)) for row in result.result_rows]


def bootstrap_existing_tables() -> None:
    """Idempotently create the DB + 8 existing tables and load their parquet
    data, by shelling out to the vendored load.sh (keeps one source of truth
    for the load logic instead of re-implementing parquet insert here).
    Operator entry point documented in docs/CUJ1.md; no application caller."""
    db = os.environ.get("CLICKHOUSE_DATABASE", "clickathon")
    # 9440 is ClickHouse Cloud's fixed native-protocol (TCP) port used by the
    # clickhouse-client CLI. It is distinct from CLICKHOUSE_PORT (8443), which
    # is the HTTPS port used by get_client()'s clickhouse_connect HTTP client.
    ch_cmd = (
        f"clickhouse-client --host {os.environ['CLICKHOUSE_HOST']} "
        f"--port 9440 "
        f"--user {os.environ['CLICKHOUSE_USER']} "
        f"--password {os.environ['CLICKHOUSE_PASSWORD']} --secure"
    )
    subprocess.run(
        [str(paths.LOAD_SH)],
        env={**os.environ, "CH": ch_cmd, "DB": db},
        check=True,
    )
