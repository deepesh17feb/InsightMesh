import argparse
import json
import sys

from atlys_agentic import paths


def assemble(spec_id: str, ddl: str, insight_md: str, trace_json: dict) -> dict:
    out_dir = paths.SUBMISSION_DIR / spec_id
    out_dir.mkdir(parents=True, exist_ok=True)

    schema_path = out_dir / "schema.sql"
    insight_path = out_dir / "insight.md"
    trace_path = out_dir / "trace.json"

    schema_path.write_text(ddl)
    insight_path.write_text(insight_md)
    trace_path.write_text(json.dumps(trace_json, indent=2, default=str))

    return {"schema": schema_path, "insight": insight_path, "trace": trace_path}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Assemble submission/<spec_id>/{schema.sql,insight.md,trace.json}")
    parser.add_argument("--spec_id", required=True)
    parser.add_argument("--ddl_file", required=True)
    parser.add_argument("--insight_file", required=True)
    parser.add_argument("--trace_file", required=True)
    args = parser.parse_args(argv)

    ddl = paths.ATLYS_AGENTIC_DIR.joinpath(args.ddl_file).read_text()
    insight_md = paths.ATLYS_AGENTIC_DIR.joinpath(args.insight_file).read_text()
    trace_json = json.loads(paths.ATLYS_AGENTIC_DIR.joinpath(args.trace_file).read_text())

    written = assemble(args.spec_id, ddl, insight_md, trace_json)
    for label, path in written.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
