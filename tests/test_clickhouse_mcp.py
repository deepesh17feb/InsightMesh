"""Unit tests for the ClickHouse Model Context Protocol (MCP) Server and Client Adapter."""
import pytest

from atlys_agentic import clickhouse_mcp, mcp_server


def test_mcp_server_initialization():
    """Verify that ClickHouse FastMCP server is initialized with expected metadata."""
    server = mcp_server.mcp_server
    assert server.name == "clickhouse-mcp"


def test_mcp_execute_query_rejects_non_select():
    """Verify that MCP execute_query tool enforces read-only SELECT security policy."""
    with pytest.raises(ValueError, match="SELECT"):
        mcp_server.execute_query("DROP TABLE important_data")


def test_mcp_client_adapter_execute_query():
    """Verify that ClickHouseMCPClient executes SELECT queries properly."""
    client = clickhouse_mcp.get_mcp_client()
    res = client.execute_query("SELECT 1 AS col")
    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0].get("col") == 1


def test_mcp_client_list_tables():
    """Verify that ClickHouseMCPClient list_tables returns a list."""
    client = clickhouse_mcp.get_mcp_client()
    tables = client.list_tables()
    assert isinstance(tables, list)
