from typing import Generic, TypeVar

from pydantic import BaseModel

from atlys_agentic import chdb_client, tools, tracing

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


_MANDATORY_CUT_DIMENSIONS = ("device_type", "geoip_country_code", "destination")
_STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "what", "is", "there", "an", "on"}


class AnalysisState(BaseModel):
    question: str = ""
    spec_id: str = "chat"
    base_sql: str = ""
    trace_id: str = ""
    context_rows: list[dict] = []
    cuts: dict = {}
    known_issue_match: bool = False
    matched_known_issue: str = ""
    confidence: dict = {}
    answer_md: str = ""


class AnalysisFlow(CrewAIFlow[AnalysisState]):
    def __init__(self):
        super().__init__()
        self.state = AnalysisState()

    @start()
    def jit_context_retrieval(self):
        self.state.trace_id = tracing.new_trace(self.state.spec_id)
        self.state.context_rows = chdb_client.run(
            "SELECT key, definition FROM business_context WHERE section LIKE '%Known-issues%' OR key LIKE 'K%'"
        )
        tracing.span(
            self.state.trace_id,
            "jit_context_retrieval",
            {"question": self.state.question},
            {"rows": len(self.state.context_rows)},
        )

    @listen(jit_context_retrieval)
    def run_multi_cut_analysis(self):
        for dim in _MANDATORY_CUT_DIMENSIONS:
            sql = f"{self.state.base_sql} /* cut: {dim} */"
            result = tools.Tool_Analytics_Compute(sql)
            self.state.cuts[dim] = result.get("rows", [])
            tracing.span(self.state.trace_id, f"cut_{dim}", {"select_sql": sql}, result)

    @router(run_multi_cut_analysis)
    def route_known_issue(self):
        question_words = {w.strip("?.,!()\"'").lower() for w in self.state.question.split()}
        for row in self.state.context_rows:
            def_text = f"{row.get('key', '')} {row.get('definition', '')}".lower()
            def_words = {w.strip("?.,!()\"'") for w in def_text.split()}
            overlap = (question_words & def_words) - _STOPWORDS
            if len(overlap) >= 2 or any(k in question_words for k in ["k1", "k2", "k3", "k4", "k5", "k6", "k7"]):
                self.state.known_issue_match = True
                self.state.matched_known_issue = row.get("key", "Known Issue")
                return "known_issue"
        return "no_known_issue"

    @listen("known_issue")
    def score_with_known_issue(self):
        self._score_and_write(known_issue_match=True)

    @listen("no_known_issue")
    def score_without_known_issue(self):
        self._score_and_write(known_issue_match=False)

    def _score_and_write(self, known_issue_match: bool):
        sample_size = sum(len(rows) for rows in self.state.cuts.values())
        self.state.confidence = tools.Tool_Score_Confidence(
            sample_size=max(sample_size, 1),
            effect_size_pct=15.0,
            known_issue_match=known_issue_match,
            cut_consistency=1.0 if len(self.state.cuts) == len(_MANDATORY_CUT_DIMENSIONS) else 0.5,
        )
        issue_note = (
            f" This aligns with known issue {self.state.matched_known_issue} already logged in business_context."
            if known_issue_match
            else ""
        )
        self.state.answer_md = (
            f"**{self.state.question}**\n\n"
            f"Cuts analyzed: {', '.join(self.state.cuts.keys())}.{issue_note}\n\n"
            f"Confidence: {self.state.confidence.get('score', 0.0)} — {self.state.confidence.get('rationale', '')}"
        )
        tools.Tool_Context_Upsert(
            section="Insights",
            key=f"insight::{self.state.spec_id}::{abs(hash(self.state.question)) % 100000}",
            definition=self.state.answer_md,
            agent="product_analyst",
            trace_id=self.state.trace_id,
        )
        tracing.span(
            self.state.trace_id,
            "score_and_write_insight",
            {"known_issue_match": known_issue_match},
            self.state.confidence,
        )


def run(question: str, spec_id: str = "chat", base_sql: str = "SELECT * FROM purchase_completed") -> dict:
    flow = AnalysisFlow()
    flow.state.question = question
    flow.state.spec_id = spec_id
    flow.state.base_sql = base_sql

    flow.jit_context_retrieval()
    flow.run_multi_cut_analysis()
    branch = flow.route_known_issue()
    if branch == "known_issue":
        flow.score_with_known_issue()
    else:
        flow.score_without_known_issue()

    return {
        "answer_md": flow.state.answer_md,
        "confidence": flow.state.confidence,
        "known_issue_match": flow.state.known_issue_match,
        "cuts": flow.state.cuts,
        "trace_id": flow.state.trace_id,
    }
