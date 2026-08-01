import argparse
import sys

from atlys_agentic import chdb_client
from atlys_agentic.flows import ingestion_flow


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CUJ1: ingest a feature spec into ClickHouse Cloud (HITL-gated).")
    parser.add_argument("--spec_dir", required=True, help='e.g. "specs/01_express_checkout"')
    parser.add_argument("--table", required=True, help="destination ClickHouse table name")
    args = parser.parse_args(argv)

    spec_id = args.spec_dir.rstrip("/").split("/")[-1]

    chdb_client.init_schema()
    chdb_client.init_base_context()

    result = ingestion_flow.run(spec_id=spec_id, table_name=args.table)
    return 0 if result["approved"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
