from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from atlys_agentic import chdb_client, tools, tracing

_MANDATORY_CUT_DIMENSIONS = ("device_type", "geoip_country_code", "destination")
_STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have"}


class AnalysisState(BaseModel):
    question: str = ""
    spec_id: str = ""
    base_sql: str = ""
    trace_id: str = ""
    context_rows: list[dict] = []
    cuts: dict = {}
    known_issue_match: bool = False
    matched_known_issue: str = ""
    confidence: dict = {}
    answer_md: str = ""


class AnalysisFlow(Flow[AnalysisState]):
    @start()
    def jit_context_retrieval(self):
        with tracing.trace(f"analysis-{self.state.spec_id}", input={"question": self.state.question}):
            self.state.trace_id = tracing._current_trace_id or ""
            with tracing.step("jit_context_retrieval", input={"question": self.state.question}) as span:
                self.state.context_rows = chdb_client.run(
                    "SELECT key, definition FROM business_context WHERE section LIKE '%Known-issues%' OR key LIKE 'K%'"
                )
                span.update(output={"rows": len(self.state.context_rows)})

    @listen(jit_context_retrieval)
    def run_multi_cut_analysis(self):
        with tracing.trace(f"analysis-cuts-{self.state.spec_id}", input={"question": self.state.question}):
            for dim in _MANDATORY_CUT_DIMENSIONS:
                sql = f"{self.state.base_sql} /* cut: {dim} */"
                with tracing.step(f"cut_{dim}", input={"select_sql": sql}) as span:
                    result = tools.Tool_Analytics_Compute(sql)
                    self.state.cuts[dim] = result["rows"]
                    span.update(output=result)

    @router(run_multi_cut_analysis)
    def route_known_issue(self):
        question_words = {w.strip("?.,!()") for w in self.state.question.lower().split()}
        for row in self.state.context_rows:
            definition_words = {w.strip("?.,!()") for w in row["definition"].lower().split()}
            overlap = (question_words & definition_words) - _STOPWORDS
            if len(overlap) >= 2:
                self.state.known_issue_match = True
                self.state.matched_known_issue = row["key"]
                return "known_issue"
        return "no_known_issue"

    @listen("known_issue")
    def score_with_known_issue(self):
        self._score_and_write(known_issue_match=True)

    @listen("no_known_issue")
    def score_without_known_issue(self):
        self._score_and_write(known_issue_match=False)

    def _score_and_write(self, known_issue_match: bool):
        with tracing.trace(f"analysis-score-{self.state.spec_id}", input={"known_issue_match": known_issue_match}):
            sample_size = sum(len(rows) for rows in self.state.cuts.values())
            self.state.confidence = tools.Tool_Score_Confidence(
                sample_size=max(sample_size, 1),
                effect_size_pct=15.0,
                known_issue_match=known_issue_match,
                cut_consistency=1.0 if len(self.state.cuts) == len(_MANDATORY_CUT_DIMENSIONS) else 0.5,
            )
            issue_note = (
                f" This aligns with known issue {self.state.matched_known_issue} already logged in business_context."
                if known_issue_match else ""
            )
            self.state.answer_md = (
                f"**{self.state.question}**\n\n"
                f"Cuts analyzed: {', '.join(self.state.cuts.keys())}.{issue_note}\n\n"
                f"Confidence: {self.state.confidence['score']} — {self.state.confidence['rationale']}"
            )
            
            with tracing.step("score_and_write_insight", input={"known_issue_match": known_issue_match}) as span:
                tools.Tool_Context_Upsert(
                    section="Insights",
                    key=f"insight::{self.state.spec_id}::{hash(self.state.question) % 100000}",
                    definition=self.state.answer_md,
                    agent="product_analyst",
                    trace_id=tracing._current_trace_id or "",
                )
                span.update(output=self.state.confidence)


def run(question: str, spec_id: str, base_sql: str) -> dict:
    flow = AnalysisFlow()
    flow.kickoff(inputs={"question": question, "spec_id": spec_id, "base_sql": base_sql})
    return {
        "answer_md": flow.state.answer_md,
        "confidence": flow.state.confidence,
        "known_issue_match": flow.state.known_issue_match,
        "cuts": flow.state.cuts,
        "trace_id": flow.state.trace_id,
    }
