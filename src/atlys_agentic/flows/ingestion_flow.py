"""CUJ 1 — Feature Ingestion & Context Audit Pipeline.

A deterministic, hand-sequenced pipeline: every step below is a plain
Python method called in a fixed order by `run()`. There is no agentic
tool-selection loop and no CrewAI Flow event graph — narration calls
(`narration.narrate`) produce PM-readable prose from tool output, but the
pipeline's control flow never depends on an LLM's decision. This is a
deliberate choice for a path that is one `APPROVE` away from mutating
production ClickHouse Cloud schema: determinism and auditability outrank
agent autonomy here. See docs/cuj_architecture_v2.md.
"""
import os
from typing import Callable

from pydantic import BaseModel

from atlys_agentic import agents, narration, paths, prompts, tools, tracing


class IngestionState(BaseModel):
    spec_id: str = ""
    table_name: str = ""
    ddl: str = ""
    mv_ddl: str = ""
    approved: bool = False
    dry_run: bool = False
    trace_id: str = ""
    ddl_result: dict = {}
    diff_result: dict = {}
    table_consultation: dict = {}
    reasoning: dict = {}


class IngestionFlow:
    input_fn: Callable[[str], str] = staticmethod(input)

    def __init__(self):
        self.state = IngestionState()

    def instrumentation_step(self):
        """Step 1: consult existing chDB/ClickHouse metadata, then design schema, MV, and 6-pillar decision."""
        mode = "dry_run" if self.state.dry_run else "live_run"
        self.state.trace_id = tracing.new_trace(self.state.spec_id, run_mode=mode)
        ndjson_path = paths.events_ndjson(self.state.spec_id)
        spec_text = paths.spec_md(self.state.spec_id).read_text(encoding="utf-8")
        if not self.state.table_name:
            self.state.table_name = tools.Tool_Infer_Table_Name(self.state.spec_id, spec_text)

        librarian_cfg = agents.get_role_config("context_librarian")
        engineer_cfg = agents.get_role_config("instrumentation_engineer")

        # 1. Consult existing chDB and ClickHouse metadata
        preliminary_cols = []
        self.state.table_consultation = tools.Tool_Consult_Internal_Tables(
            self.state.spec_id, preliminary_cols, self.state.table_name
        )

        narration.narrate(
            librarian_cfg,
            (
                f"Incoming Feature Spec: '{self.state.spec_id}' (Target Table: '{self.state.table_name}')\n"
                f"Consultation data from schema_registry & business_context:\n"
                f"{self.state.table_consultation}\n\n"
                f"Summarize the existing table versions, column overlap, and known metric rules for the Instrumentation Engineer."
            ),
            run_mode=mode,
            span_name="context_librarian::consult_context",
            trace_id=self.state.trace_id,
        )

        # 2. Infer production ClickHouse DDL & Materialized View
        self.state.ddl = tools.Tool_Infer_Schema(ndjson_path, spec_text, self.state.table_name)
        self.state.mv_ddl = tools.Tool_Generate_MV(self.state.table_name, self.state.ddl)

        # 3. Grounded consultation with the full inferred column set
        cols = tools._columns_from_ddl(self.state.ddl)
        self.state.table_consultation = tools.Tool_Consult_Internal_Tables(
            self.state.spec_id, cols, self.state.table_name
        )
        self.state.reasoning = tools.Tool_Explain_Schema_Rationale(
            self.state.table_name,
            self.state.ddl,
            self.state.mv_ddl,
            self.state.table_consultation,
            spec_text,
        )

        # 4. Narrated architectural decision
        design_prompt = prompts.build_instrumentation_engineer_prompt(
            spec_id=self.state.spec_id,
            table_name=self.state.table_name,
            ddl=self.state.ddl,
            strategy=self.state.table_consultation.get("strategy", "CREATE_NEW"),
            recommendation=self.state.table_consultation.get("recommendation", ""),
        )
        llm_reasoning = narration.narrate(
            engineer_cfg,
            design_prompt,
            run_mode=mode,
            span_name="instrumentation_engineer::schema_design",
            trace_id=self.state.trace_id,
        )
        if llm_reasoning:
            self.state.reasoning["high_level_summary"] = llm_reasoning
            self.state.reasoning["llm_architectural_decision"] = llm_reasoning

        tracing.span(
            self.state.trace_id,
            "instrumentation_step",
            {"spec_id": self.state.spec_id, "table": self.state.table_name},
            {
                "ddl": self.state.ddl,
                "table_strategy": self.state.table_consultation.get("strategy"),
                "context_consulted_via": librarian_cfg["role"],
                "agent": engineer_cfg["role"],
            },
            run_mode=mode,
        )
        return self.state.ddl

    def context_step(self):
        """Step 2: diff proposed schema against chDB business_context and audit integrity."""
        mode = "dry_run" if self.state.dry_run else "live_run"
        columns = tools._columns_from_ddl(self.state.ddl)
        self.state.diff_result = tools.Tool_Context_Diff(self.state.table_name, columns)

        librarian_cfg = agents.get_role_config("context_librarian")
        diff = self.state.diff_result or {}
        audit_prompt = prompts.build_context_librarian_prompt(
            spec_id=self.state.spec_id,
            table_name=self.state.table_name,
            additions=diff.get("additions", []),
            conflicts=diff.get("conflicts", []),
            gaps=diff.get("gaps", []),
        )
        librarian_summary = narration.narrate(
            librarian_cfg,
            audit_prompt,
            run_mode=mode,
            span_name="context_librarian::context_audit",
            trace_id=self.state.trace_id,
        )
        if librarian_summary:
            self.state.diff_result["llm_integrity_audit"] = librarian_summary

        tracing.span(
            self.state.trace_id,
            "context_step",
            {"table": self.state.table_name, "dry_run": self.state.dry_run},
            {"diff": self.state.diff_result, "agent": librarian_cfg["role"]},
            run_mode=mode,
        )
        return self.state.diff_result

    def format_proposal_summary(self) -> str:
        """Format the complete Instrumentation Engineer decision breakdown and context diff for operator review."""
        consult = self.state.table_consultation or {}
        reasoning = self.state.reasoning or {}
        deep = reasoning.get("technical_deep_dive") or {}
        diff = self.state.diff_result or {}

        summary_lines = [
            "=" * 80,
            "🧠 INSTRUMENTATION ENGINEER ARCHITECTURAL DECISION & RATIONALE",
            "=" * 80,
            f"• Target Table: {self.state.table_name}",
            f"• Executive Summary: {reasoning.get('high_level_summary', '')}",
            "",
            "--- 1. Table Strategy Decision ---",
            f"  Strategy: {consult.get('strategy', 'CREATE_NEW')}",
            f"  Recommendation: {consult.get('recommendation', '')}",
            "",
            "--- 2. Primary Sorting Key (ORDER BY) ---",
            f"  {deep.get('ordering_mechanics', reasoning.get('ordering_reasoning', ''))}",
            "",
            "--- 3. Partitioning Strategy (PARTITION BY) ---",
            f"  {deep.get('partitioning_mechanics', reasoning.get('partitioning_reasoning', ''))}",
            "",
            "--- 4. Encodings & Data Types ---",
            f"  {deep.get('column_encodings_and_compression', reasoning.get('types_reasoning', ''))}",
            "",
            "--- 5. Materialized View Rollup ---",
            f"  {deep.get('materialized_view_rollup', reasoning.get('mv_reasoning', ''))}",
            "",
            "--- 6. Data Lifecycle Retention (TTL) ---",
            f"  {deep.get('lifecycle_retention', reasoning.get('retention_reasoning', ''))}",
            "",
            "--- Proposed ClickHouse DDL ---",
            self.state.ddl,
        ]

        if self.state.mv_ddl:
            summary_lines.extend([
                "",
                "--- Proposed Materialized View (SummingMergeTree) ---",
                self.state.mv_ddl,
            ])

        additions = diff.get("additions", [])
        conflicts = diff.get("conflicts", [])
        gaps = diff.get("gaps", [])

        summary_lines.extend([
            "",
            "--- Context Diff Audit (Context Librarian) ---",
            f"  • New Attributes to Sync ({len(additions)}): {', '.join(additions) if additions else 'None'}",
            f"  • Metric Conflicts Detected: {', '.join(conflicts) if conflicts else 'None'}",
            f"  • Undocumented Gaps Flagged: {', '.join(gaps) if gaps else 'None'}",
            "=" * 80,
        ])
        return "\n".join(summary_lines)

    def human_gate(self):
        """Step 3: Human-in-the-Loop review presenting the complete proposal. Hard stop — only the literal string 'APPROVE' passes."""
        if not self.state.diff_result:
            self.context_step()

        print("\n" + self.format_proposal_summary())

        if self.state.dry_run:
            prompt_text = (
                "\n[DRY RUN MODE — Non-Mutating Proposal Review]\n"
                "Type APPROVE to confirm proposal review (or press Enter/reject to abort): "
            )
            answer = self.input_fn(prompt_text)
            self.state.approved = answer == "APPROVE"
            tracing.span(
                self.state.trace_id,
                "human_gate_dry_run",
                {"prompt_answer": answer, "dry_run": True},
                {"approved": self.state.approved},
                run_mode="dry_run",
            )
        else:
            prompt_text = (
                "\n[LIVE DEPLOYMENT MODE]\n"
                "Type APPROVE to execute on ClickHouse Cloud: "
            )
            answer = self.input_fn(prompt_text)
            self.state.approved = answer == "APPROVE"
            tracing.span(
                self.state.trace_id,
                "human_gate",
                {"prompt_answer": answer, "dry_run": False},
                {"approved": self.state.approved},
                run_mode="live_run",
            )

    def route_gate(self) -> str:
        """Step 4: route based on operator authorization."""
        return "approved" if self.state.approved else "rejected"

    def execute_and_audit(self):
        """Step 5a: execute DDL on ClickHouse Cloud, register the schema version, and sync business_context.
        Each write is a separate tool call so a partial failure is attributable to the write that actually failed."""
        ddl_result = tools.Tool_Execute_DDL(self.state.ddl, self.state.table_name, self.state.spec_id)
        if ddl_result.get("status") == "ok":
            registry_result = tools.Tool_Register_Schema_Version(self.state.ddl, self.state.table_name, self.state.spec_id)
            ddl_result["version"] = registry_result.get("version")
        self.state.ddl_result = ddl_result
        tracing.span(
            self.state.trace_id,
            "execute_ddl",
            {"table": self.state.table_name},
            self.state.ddl_result,
            run_mode="live_run",
        )

        if self.state.mv_ddl and self.state.ddl_result.get("status") == "ok":
            mv_table = f"{self.state.table_name}_daily_mv"
            mv_result = tools.Tool_Execute_DDL(self.state.mv_ddl, mv_table, self.state.spec_id)
            if mv_result.get("status") == "ok":
                tools.Tool_Register_Schema_Version(self.state.mv_ddl, mv_table, self.state.spec_id)

        if not self.state.diff_result:
            columns = tools._columns_from_ddl(self.state.ddl)
            self.state.diff_result = tools.Tool_Context_Diff(self.state.table_name, columns)
            tracing.span(
                self.state.trace_id,
                "context_diff",
                {"table": self.state.table_name},
                self.state.diff_result,
                run_mode="live_run",
            )
        for addition in self.state.diff_result.get("additions", []):
            if "." in addition:
                table, col = addition.split(".", 1)
            else:
                table, col = self.state.table_name, addition
            definition = f"New column from {self.state.spec_id}: {col} on {table}."
            before = tools._latest_context_definition(addition)
            tools.Tool_Context_Upsert(
                section="Event tables",
                key=addition,
                definition=definition,
                agent="context_librarian",
                trace_id=self.state.trace_id,
            )
            tools.Tool_Append_Context_Changelog(
                key=addition,
                before=before,
                after=definition,
                agent="context_librarian",
                trace_id=self.state.trace_id,
            )
        print(f"\n🎉 Context Librarian successfully deployed table '{self.state.table_name}' to ClickHouse Cloud and updated chDB.")

    def dry_run_approved(self):
        tracing.span(
            self.state.trace_id,
            "dry_run_proposal_approved",
            {"table": self.state.table_name},
            {"approved": True, "dry_run": True},
            run_mode="dry_run",
        )
        print(f"\n✅ Dry-run proposal for '{self.state.table_name}' reviewed and approved by operator. (ClickHouse Cloud and chDB remain untouched).")

    def dry_run_aborted(self):
        tracing.span(
            self.state.trace_id,
            "dry_run_proposal_rejected",
            {"table": self.state.table_name},
            {"approved": False, "dry_run": True},
            run_mode="dry_run",
        )
        print(f"\n❌ Dry-run proposal review for '{self.state.table_name}' aborted by operator.")

    def abort(self):
        tracing.span(
            self.state.trace_id,
            "human_gate_rejected",
            {"table": self.state.table_name},
            {"approved": False},
            run_mode="live_run",
        )
        print(f"\n❌ DDL for {self.state.table_name} rejected. Ingestion aborted.")


def run(
    spec_id: str,
    table_name: str = None,
    input_fn: Callable[[str], str] = None,
    dry_run: bool = False,
    **kwargs,
) -> dict:
    flow = IngestionFlow()
    if input_fn is not None:
        flow.input_fn = input_fn
    elif dry_run:
        flow.input_fn = lambda _: "APPROVE"
    else:
        flow.input_fn = input

    flow.state.spec_id = spec_id
    flow.state.table_name = table_name or ""
    flow.state.dry_run = dry_run

    mode = "dry_run" if dry_run else "live_run"
    with tracing.trace(
        f"clickathon-{mode}-{spec_id}",
        input={"spec_id": spec_id, "table_name": table_name, "dry_run": dry_run},
        run_mode=mode,
    ):
        flow.instrumentation_step()
        flow.context_step()
        flow.human_gate()
        branch = flow.route_gate()
        if branch == "approved":
            if not dry_run:
                flow.execute_and_audit()
            else:
                flow.dry_run_approved()
        else:
            if not dry_run:
                flow.abort()
            else:
                flow.dry_run_aborted()

    return {
        "table_name": flow.state.table_name,
        "approved": flow.state.approved,
        "dry_run": flow.state.dry_run,
        "ddl": flow.state.ddl,
        "mv_ddl": flow.state.mv_ddl,
        "table_consultation": flow.state.table_consultation,
        "reasoning": flow.state.reasoning,
        "ddl_result": flow.state.ddl_result,
        "diff_result": flow.state.diff_result,
        "trace_id": flow.state.trace_id,
    }
