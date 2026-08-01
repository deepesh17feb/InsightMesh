from typing import Callable

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from atlys_agentic import paths, tools, tracing


class IngestionState(BaseModel):
    spec_id: str = ""
    table_name: str = ""
    ddl: str = ""
    mv_ddl: str = ""
    approved: bool = False
    trace_id: str = ""
    ddl_result: dict = {}
    diff_result: dict = {}


class IngestionFlow(Flow[IngestionState]):
    input_fn: Callable[[str], str] = staticmethod(input)

    @start()
    def infer_schema(self):
        with tracing.trace(f"ingestion-{self.state.spec_id}", input={"spec_id": self.state.spec_id, "table": self.state.table_name}):
            self.state.trace_id = tracing._current_trace_id or ""
            with tracing.step("infer_schema", input={"spec_id": self.state.spec_id}) as span:
                ndjson_path = paths.events_ndjson(self.state.spec_id)
                spec_text = paths.spec_md(self.state.spec_id).read_text(encoding="utf-8")
                self.state.ddl = tools.Tool_Infer_Schema(ndjson_path, spec_text, self.state.table_name)
                self.state.mv_ddl = tools.Tool_Generate_MV(self.state.table_name, self.state.ddl)
                span.update(output={"ddl": self.state.ddl})
        return self.state.ddl

    @listen(infer_schema)
    def human_gate(self):
        print("\n--- Proposed DDL ---\n" + self.state.ddl)
        if self.state.mv_ddl:
            print("\n--- Proposed Materialized View ---\n" + self.state.mv_ddl)
        answer = self.input_fn("Type APPROVE to execute on ClickHouse Cloud: ")
        self.state.approved = answer == "APPROVE"

    @router(human_gate)
    def route_gate(self):
        return "approved" if self.state.approved else "rejected"

    @listen("approved")
    def execute_and_audit(self):
        with tracing.trace(f"ingestion-audit-{self.state.spec_id}", input={"spec_id": self.state.spec_id}):
            with tracing.step("execute_ddl", input={"table": self.state.table_name}) as span:
                self.state.ddl_result = tools.Tool_Execute_DDL(self.state.ddl, self.state.table_name, self.state.spec_id)
                span.update(output=self.state.ddl_result)

            if self.state.mv_ddl and self.state.ddl_result["status"] == "ok":
                with tracing.step("execute_mv_ddl", input={"table": f"{self.state.table_name}_daily_mv"}):
                    tools.Tool_Execute_DDL(self.state.mv_ddl, f"{self.state.table_name}_daily_mv", self.state.spec_id)

            with tracing.step("context_diff", input={"table": self.state.table_name}) as span:
                columns = tools._columns_from_ddl(self.state.ddl)
                self.state.diff_result = tools.Tool_Context_Diff(self.state.table_name, columns)
                span.update(output=self.state.diff_result)

            for addition in self.state.diff_result["additions"]:
                table, col = addition.split(".", 1)
                tools.Tool_Context_Upsert(
                    section="Event tables",
                    key=addition,
                    definition=f"New column from {self.state.spec_id}: {col} on {table}.",
                    agent="context_librarian",
                    trace_id=tracing._current_trace_id or "",
                )

    @listen("rejected")
    def abort(self):
        print(f"DDL for {self.state.table_name} rejected. Ingestion aborted.")


def run(spec_id: str, table_name: str, input_fn: Callable[[str], str] = input) -> dict:
    flow = IngestionFlow()
    flow.input_fn = input_fn
    flow.kickoff(inputs={"spec_id": spec_id, "table_name": table_name})
    return {
        "approved": flow.state.approved,
        "ddl": flow.state.ddl,
        "ddl_result": flow.state.ddl_result,
        "diff_result": flow.state.diff_result,
        "trace_id": flow.state.trace_id,
    }
