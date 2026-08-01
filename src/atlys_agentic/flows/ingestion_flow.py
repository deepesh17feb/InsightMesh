from typing import Callable, Generic, TypeVar

from pydantic import BaseModel

from atlys_agentic import paths, tools, tracing

T = TypeVar("T")

try:
    from crewai.flow.flow import Flow as CrewAIFlow, listen, router, start
except ImportError:  # pragma: no cover
    def start():
        def decorator(fn):
            fn._flow_step = "start"
            return fn
        return decorator

    def listen(target=None):
        def decorator(fn):
            fn._flow_step = "listen"
            fn._listen_target = target
            return fn
        return decorator

    def router(target=None):
        def decorator(fn):
            fn._flow_step = "router"
            fn._router_target = target
            return fn
        return decorator

    class CrewAIFlow(Generic[T]):  # type: ignore
        def __init__(self):
            self.state = None

        def kickoff(self, inputs: dict = None):
            pass


class IngestionState(BaseModel):
    spec_id: str = ""
    table_name: str = ""
    ddl: str = ""
    mv_ddl: str = ""
    approved: bool = False
    trace_id: str = ""
    ddl_result: dict = {}
    diff_result: dict = {}


class IngestionFlow(CrewAIFlow[IngestionState]):
    input_fn: Callable[[str], str] = staticmethod(input)

    def __init__(self):
        super().__init__()
        # crewai's typed Flow (Flow[IngestionState]) auto-creates `state` from the
        # generic parameter and exposes it as a read-only property (no setter).
        # Assigning self.state here raises AttributeError on modern crewai; only
        # initialise manually for the no-crewai fallback base class.
        if getattr(self, "state", None) is None:
            try:
                self.state = IngestionState()
            except AttributeError:
                pass

    @start()
    def infer_schema(self):
        self.state.trace_id = tracing.new_trace(self.state.spec_id)
        ndjson_path = paths.events_ndjson(self.state.spec_id)
        spec_text = paths.spec_md(self.state.spec_id).read_text(encoding="utf-8")
        self.state.ddl = tools.Tool_Infer_Schema(ndjson_path, spec_text, self.state.table_name)
        self.state.mv_ddl = tools.Tool_Generate_MV(self.state.table_name, self.state.ddl)
        tracing.span(self.state.trace_id, "infer_schema", {"spec_id": self.state.spec_id}, {"ddl": self.state.ddl})
        return self.state.ddl

    @listen(infer_schema)
    def human_gate(self):
        print("\n--- Proposed DDL ---\n" + self.state.ddl)
        if self.state.mv_ddl:
            print("\n--- Proposed Materialized View ---\n" + self.state.mv_ddl)
        answer = self.input_fn("Type APPROVE to execute on ClickHouse Cloud: ")
        self.state.approved = answer == "APPROVE"
        tracing.span(self.state.trace_id, "human_gate", {"prompt_answer": answer}, {"approved": self.state.approved})

    @router(human_gate)
    def route_gate(self):
        return "approved" if self.state.approved else "rejected"

    @listen("approved")
    def execute_and_audit(self):
        self.state.ddl_result = tools.Tool_Execute_DDL(self.state.ddl, self.state.table_name, self.state.spec_id)
        tracing.span(self.state.trace_id, "execute_ddl", {"table": self.state.table_name}, self.state.ddl_result)

        if self.state.mv_ddl and self.state.ddl_result.get("status") == "ok":
            tools.Tool_Execute_DDL(self.state.mv_ddl, f"{self.state.table_name}_daily_mv", self.state.spec_id)

        columns = tools._columns_from_ddl(self.state.ddl)
        self.state.diff_result = tools.Tool_Context_Diff(self.state.table_name, columns)
        tracing.span(self.state.trace_id, "context_diff", {"table": self.state.table_name}, self.state.diff_result)
        for addition in self.state.diff_result.get("additions", []):
            if "." in addition:
                table, col = addition.split(".", 1)
            else:
                table, col = self.state.table_name, addition
            tools.Tool_Context_Upsert(
                section="Event tables",
                key=addition,
                definition=f"New column from {self.state.spec_id}: {col} on {table}.",
                agent="context_librarian",
                trace_id=self.state.trace_id,
            )

    @listen("rejected")
    def abort(self):
        tracing.span(self.state.trace_id, "human_gate_rejected", {"table": self.state.table_name}, {"approved": False})
        print(f"DDL for {self.state.table_name} rejected. Ingestion aborted.")


def run(spec_id: str, table_name: str, input_fn: Callable[[str], str] = input) -> dict:
    flow = IngestionFlow()
    flow.input_fn = input_fn
    flow.state.spec_id = spec_id
    flow.state.table_name = table_name

    # Step through the flow sequence deterministically
    flow.infer_schema()
    flow.human_gate()
    branch = flow.route_gate()
    if branch == "approved":
        flow.execute_and_audit()
    else:
        flow.abort()

    return {
        "approved": flow.state.approved,
        "ddl": flow.state.ddl,
        "ddl_result": flow.state.ddl_result,
        "diff_result": flow.state.diff_result,
        "trace_id": flow.state.trace_id,
    }
