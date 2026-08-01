import os
import pytest
from atlys_agentic import ch_client

pytestmark = pytest.mark.skipif(
    not os.getenv("CLICKHOUSE_HOST"),
    reason="requires live ClickHouse Cloud credentials in atlys_agentic/config/.env",
)


import shutil


def test_select_round_trip():
    rows = ch_client.select("SELECT 1 AS one")
    assert rows == [{"one": 1}]


@pytest.mark.skipif(
    not shutil.which("clickhouse-client"),
    reason="clickhouse-client CLI not installed on host machine",
)
def test_bootstrap_loads_eight_tables_with_expected_row_count():
    ch_client.bootstrap_existing_tables()
    rows = ch_client.select("SELECT count() AS c FROM destination_card_clicked")
    assert rows[0]["c"] > 0
