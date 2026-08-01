"""CUJ 1: Ingestion Pipeline CLI Entrypoint.

Usage:
  python -m atlys_agentic.run_ingestion --spec_dir specs/01_express_checkout --table express_checkout
"""
import argparse
import sys

from atlys_agentic import chdb_client
from atlys_agentic.flows import ingestion_flow


def main(argv: list[str] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="CUJ 1: Ingest a feature spec and events into ClickHouse Cloud (HITL-gated)."
    )
    parser.add_argument(
        "--spec_dir",
        required=True,
        help='Spec directory path or identifier, e.g. "specs/01_express_checkout" or "01_express_checkout"',
    )
    parser.add_argument(
        "--table",
        required=True,
        help="Destination ClickHouse table name (e.g. express_checkout)",
    )
    args = parser.parse_args(argv)

    spec_id = args.spec_dir.rstrip("/").split("/")[-1]

    chdb_client.init_schema()
    chdb_client.init_base_context()

    result = ingestion_flow.run(spec_id=spec_id, table_name=args.table)
    return 0 if result["approved"] else 1


if __name__ == "__main__":
    sys.exit(main())
