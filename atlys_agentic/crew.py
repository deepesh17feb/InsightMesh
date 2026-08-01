"""Runnable CrewAI + Langfuse smoke test.

python -m atlys_agentic.crew --spec_id 01_express_checkout --table express_checkout

Wires the Instrumentation Engineer agent to the real Gemini LLM (via LiteLLM)
and traces the whole run to Langfuse: one root trace, with a nested step for
the schema-inference tool call itself. This is the first end-to-end proof
that CrewAI + Langfuse + the deterministic tools actually work together.
"""
import argparse
import sys

from crewai import Agent, Crew, Process, Task

from atlys_agentic import agents, paths, tracing


def build_crew(spec_id: str, table_name: str) -> tuple[Crew, Agent]:
    engineer = agents.build_instrumentation_engineer()

    spec_text = paths.spec_md(spec_id).read_text(encoding="utf-8")
    ndjson_path = paths.events_ndjson(spec_id)

    task = Task(
        description=(
            f"Design a ClickHouse table named `{table_name}` for this feature spec:\n\n"
            f"{spec_text}\n\n"
            f"Use the infer_schema tool with ndjson_path='{ndjson_path}', "
            f"spec_md_text=<the spec text above>, table_name='{table_name}' to get the "
            "deterministic DDL. Then explain in 3-5 sentences, for a PM audience, why the "
            "ordering key, partitioning, column types, and TTL are correct choices for this data."
        ),
        expected_output=(
            "The DDL from the infer_schema tool verbatim, followed by a short plain-language "
            "explanation of the schema design choices."
        ),
        agent=engineer,
    )

    crew = Crew(agents=[engineer], tasks=[task], process=Process.sequential, memory=False, verbose=True)
    return crew, engineer


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CrewAI + Langfuse smoke test: instrument one spec.")
    parser.add_argument("--spec_id", default="01_express_checkout")
    parser.add_argument("--table", default="express_checkout")
    args = parser.parse_args(argv)

    tracing.init_litellm_callbacks()

    with tracing.trace(
        f"instrumentation-{args.spec_id}", input={"spec_id": args.spec_id, "table": args.table}
    ) as root_span:
        crew, _ = build_crew(args.spec_id, args.table)
        with tracing.step("crew_kickoff", input={"table": args.table}) as step_span:
            result = crew.kickoff()
            step_span.update(output=str(result))
        root_span.update(output=str(result))

    print("\n=== CREW RESULT ===\n")
    print(result)
    print("\n=== LANGFUSE TRACE ===")
    print(tracing.trace_url())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
