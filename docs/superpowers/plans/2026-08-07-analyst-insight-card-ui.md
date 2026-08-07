# Analyst Insight Card UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render CUJ 2 analyst answers in the Vercel frontend as a structured 5-section Insight Card (Summary, Facts, SQL, Reasoning, Trace link) instead of a flat markdown bubble, using data the backend already computes.

**Architecture:** Backend adds one field (`trace_url`) to two places that already compute everything else. Frontend switches analyst-mode messages from the SSE-streaming chat endpoint to a plain JSON call against a new Next.js proxy route that forwards to the existing `/api/analyze/query` REST endpoint, and renders the response as a new `InsightCard` component. Instrumentation-agent mode (CUJ 1) is untouched.

**Tech Stack:** Python/FastAPI backend (`src/atlys_agentic/`), Next.js 14 App Router + Tailwind + lucide-react frontend (`frontend/`), pytest, Puppeteer (via the `mcp__puppeteer__*` tools already available in this environment) for browser-driven UI verification.

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-08-07-analyst-insight-card-ui-design.md` — read for full rationale; this plan implements it exactly, with one correction noted in Task 4 (a Next.js proxy route the design doc didn't spell out — needed because `/api/analyze/query` is a *backend* FastAPI route, and the frontend can only reach the backend through its own Next.js API routes, exactly like the existing `frontend/app/api/chat/route.ts` proxies `/v1/chat/completions`).
- No new backend dependencies. No new frontend dependencies — SQL rendering reuses existing monospace/code styling, icons come from the already-installed `lucide-react`.
- Instrumentation-agent (CUJ 1) mode must not change behavior — it stays on `/v1/chat/completions`'s SSE stream exactly as it works today.
- Backend: use `.venv/bin/python` / `.venv/bin/pytest` from the repo root for every command.
- Frontend: use `npm` from `frontend/` (Node v22, npm v11 already present; `node_modules` is not yet installed — Task 3 installs it).
- Every frontend task that changes visible UI must be verified with a real browser via the `mcp__puppeteer__*` tools (`puppeteer_navigate`, `puppeteer_screenshot`, etc.) against a running `npm run dev` server — not just `npm run build` type-checking.
- Non-analytical replies (`spec_id` in `{"conversational", "abusive_deescalation", "out_of_scope", "none"}`) must keep rendering as plain markdown, never as an Insight Card.

---

### Task 1: Backend — `trace_url` in `analysis_flow.run()`

**Files:**
- Modify: `src/atlys_agentic/flows/analysis_flow.py`
- Test: `tests/test_cuj2_analytics_flow.py` (add under the existing empty `LEVEL 3: END-TO-END WORKFLOW & PERSISTENCE` heading)

**Interfaces:**
- Produces: `analysis_flow.run(...)`'s return dict gains a `"trace_url": str` key (empty string if no trace was captured), consumed by Task 2's `/api/analyze/query` endpoint.

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_cuj2_analytics_flow.py`, replacing the empty `# LEVEL 3: END-TO-END WORKFLOW & PERSISTENCE` section header with:

```python
# ==============================================================================
# LEVEL 3: END-TO-END WORKFLOW & PERSISTENCE
# ==============================================================================


def test_run_includes_trace_url_captured_during_the_trace():
    """analysis_flow.run()'s return dict must carry trace_url (not just
    trace_id) so callers like /api/analyze/query can surface a clickable
    Langfuse link without reconstructing the URL themselves."""
    from unittest.mock import MagicMock, patch

    from atlys_agentic import chdb_client, tracing
    from atlys_agentic.flows import analysis_flow

    chdb_client.init_schema()
    chdb_client.init_base_context()

    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = MagicMock()
    mock_client.get_current_trace_id.return_value = "trace-insight-1"
    mock_client.get_trace_url.return_value = "https://us.cloud.langfuse.com/trace/trace-insight-1"

    tracing._current_trace_id = None
    tracing._current_trace_url = None

    with patch("atlys_agentic.tracing.client", return_value=mock_client):
        result = analysis_flow.run(
            question="What is the conversion rate?",
            spec_id="01_express_checkout",
            enable_guardrails=False,
        )

    assert result["trace_id"] == "trace-insight-1"
    assert result["trace_url"] == "https://us.cloud.langfuse.com/trace/trace-insight-1"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_cuj2_analytics_flow.py::test_run_includes_trace_url_captured_during_the_trace -v`
Expected: `FAILED` — `KeyError: 'trace_url'` (the key doesn't exist yet on the return dict).

- [ ] **Step 3: Add `trace_url` to the return dict**

In `src/atlys_agentic/flows/analysis_flow.py`, find the `return {...}` statement at the end of `run()` (currently lines 671-683):

```python
    return {
        "answer_md": flow.state.answer_md,
        "executive_summary": flow.state.executive_summary,
        "confidence": flow.state.confidence,
        "known_issue_match": flow.state.known_issue_match,
        "matched_known_issue": flow.state.matched_known_issue,
        "cuts": flow.state.cuts,
        "views": flow.state.views,
        "sql_queries": flow.state.sql_queries,
        "spec_id": flow.state.spec_id,
        "table_name": flow.state.table_name,
        "trace_id": flow.state.trace_id,
    }
```

Add one line, `"trace_url": tracing.trace_url() or "",` right after the `"trace_id"` line:

```python
    return {
        "answer_md": flow.state.answer_md,
        "executive_summary": flow.state.executive_summary,
        "confidence": flow.state.confidence,
        "known_issue_match": flow.state.known_issue_match,
        "matched_known_issue": flow.state.matched_known_issue,
        "cuts": flow.state.cuts,
        "views": flow.state.views,
        "sql_queries": flow.state.sql_queries,
        "spec_id": flow.state.spec_id,
        "table_name": flow.state.table_name,
        "trace_id": flow.state.trace_id,
        "trace_url": tracing.trace_url() or "",
    }
```

`tracing.trace_url()` (defined in `src/atlys_agentic/tracing.py:176-184`) is explicitly documented as "safe to call after the trace() block has exited — returns the captured trace URL", which is exactly this call site (outside the `with tracing.trace(...)` block that wraps the rest of `run()`'s body).

There are 4 other early-return dicts inside `run()` (for guardrail intents: no-question, greeting, abusive, out_of_scope — around lines 571-638). Leave those alone — they intentionally short-circuit before any trace is opened, so `trace_url` would always be empty there anyway, and the design doc's non-analytical-reply handling (Task 4) never inspects `trace_url` on those paths.

- [ ] **Step 4: Run the test again — verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cuj2_analytics_flow.py::test_run_includes_trace_url_captured_during_the_trace -v`
Expected: `1 passed`

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: same result as before this change — 5 pre-existing, unrelated failures (`test_agents.py::test_instrumentation_engineer_has_schema_tools`, `test_chat_backend.py::test_chat_completions_returns_openai_shaped_response`, `test_chdb_client.py::test_run_rejects_non_select_read_helper_still_allows_ddl`, `test_paths.py::test_unseen_spec_dir_does_not_exist_yet`, `test_tools.py::test_analytics_compute_returns_json_rows`) plus 1 new passing test, no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/atlys_agentic/flows/analysis_flow.py tests/test_cuj2_analytics_flow.py
git commit -m "$(cat <<'EOF'
feat(cuj2): add trace_url to analysis_flow.run()'s return dict

Captured via tracing.trace_url() after the trace() block exits, the
same pattern ingestion_flow.generate_proposal() already uses. Lets
callers surface a clickable Langfuse link without reconstructing the
URL themselves.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Backend — `trace_url` in `/api/analyze/query`

**Files:**
- Modify: `src/atlys_agentic/run_chat.py`
- Test: `tests/test_chat_backend.py`

**Interfaces:**
- Consumes: `analysis_flow.run(...)`'s `"trace_url"` key (Task 1).
- Produces: `POST /api/analyze/query`'s JSON response gains a `"trace_url": str` field, consumed by Task 4's frontend proxy/fetch.

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_chat_backend.py`:

```python
def test_analyze_query_endpoint_returns_trace_url():
    fake_result = {
        "answer_md": "Express lifts conversion 8% overall.",
        "executive_summary": "Express lifts conversion 8% overall.",
        "confidence": {"score": 0.75, "rationale": "r"},
        "known_issue_match": False,
        "matched_known_issue": "",
        "cuts": {"device_type": []},
        "views": {"metric_deltas": []},
        "sql_queries": ["SELECT 1"],
        "spec_id": "01_express_checkout",
        "trace_id": "trace-42",
        "trace_url": "https://us.cloud.langfuse.com/trace/trace-42",
    }
    with patch("atlys_agentic.run_chat.analysis_flow.run", return_value=fake_result) as mock_run:
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.post(
            "/api/analyze/query",
            json={"question": "Does Express lift conversion?", "spec_id": "01_express_checkout"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_url"] == "https://us.cloud.langfuse.com/trace/trace-42"
    assert body["executive_summary"] == fake_result["executive_summary"]
    mock_run.assert_called_once()
```

This uses the same `patch("atlys_agentic.run_chat.analysis_flow.run", ...)` and `TestClient` pattern the file's existing `test_chat_completions_returns_openai_shaped_response` test already uses (imports for `patch` and `app` are already at the top of the file).

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_chat_backend.py::test_analyze_query_endpoint_returns_trace_url -v`
Expected: `FAILED` — `KeyError: 'trace_url'` (the response dict doesn't include it yet).

- [ ] **Step 3: Add `trace_url` to the endpoint's response**

In `src/atlys_agentic/run_chat.py`, find the `/api/analyze/query` handler (currently lines 132-150):

```python
@app.post("/api/analyze/query")
def analyze_query(req: AnalysisRequest):
    chdb_client.init_schema()
    chdb_client.init_base_context()
    result = analysis_flow.run(question=req.question, spec_id=req.spec_id, base_sql=req.base_sql)
    return {
        "status": "success",
        "question": req.question,
        "spec_id": req.spec_id,
        "executive_summary": result.get("executive_summary", ""),
        "answer_md": result.get("answer_md", ""),
        "confidence": result.get("confidence", {}),
        "known_issue_match": result.get("known_issue_match", False),
        "matched_known_issue": result.get("matched_known_issue", ""),
        "cuts": result.get("cuts", {}),
        "views": result.get("views", {}),
        "sql_queries": result.get("sql_queries", []),
        "trace_id": result.get("trace_id", ""),
    }
```

Add one line, `"trace_url": result.get("trace_url", ""),` right after the `"trace_id"` line:

```python
@app.post("/api/analyze/query")
def analyze_query(req: AnalysisRequest):
    chdb_client.init_schema()
    chdb_client.init_base_context()
    result = analysis_flow.run(question=req.question, spec_id=req.spec_id, base_sql=req.base_sql)
    return {
        "status": "success",
        "question": req.question,
        "spec_id": req.spec_id,
        "executive_summary": result.get("executive_summary", ""),
        "answer_md": result.get("answer_md", ""),
        "confidence": result.get("confidence", {}),
        "known_issue_match": result.get("known_issue_match", False),
        "matched_known_issue": result.get("matched_known_issue", ""),
        "cuts": result.get("cuts", {}),
        "views": result.get("views", {}),
        "sql_queries": result.get("sql_queries", []),
        "trace_id": result.get("trace_id", ""),
        "trace_url": result.get("trace_url", ""),
    }
```

- [ ] **Step 4: Run the test again — verify it passes**

Run: `.venv/bin/python -m pytest tests/test_chat_backend.py::test_analyze_query_endpoint_returns_trace_url -v`
Expected: `1 passed`

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: same 5 pre-existing failures as Task 1 left it, plus 1 more new passing test, no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/atlys_agentic/run_chat.py tests/test_chat_backend.py
git commit -m "$(cat <<'EOF'
feat(cuj2): surface trace_url from /api/analyze/query

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Frontend — `InsightCard` and `InsightCardSkeleton` components

**Files:**
- Create: `frontend/app/components/InsightCard.tsx`
- Create: `frontend/app/components/InsightCardSkeleton.tsx`
- Temporary (created and deleted within this task): `frontend/app/dev-insight-preview/page.tsx`

**Interfaces:**
- Produces: `export interface Insight { question: string; executiveSummary: string; confidence: {...}; knownIssueMatch: boolean; matchedKnownIssue: string; cuts: Record<string, Array<Record<string, any>>>; views: { metric_deltas: Array<{...}> }; sqlQueries: string[]; specId: string; traceId: string; traceUrl: string; }` and `export default function InsightCard({ insight }: { insight: Insight }): JSX.Element` from `InsightCard.tsx`. `export default function InsightCardSkeleton(): JSX.Element` from `InsightCardSkeleton.tsx`. Both are pure presentational components — no data fetching, no external state. Consumed by Task 4's `page.tsx`.

- [ ] **Step 1: Install frontend dependencies**

Run: `cd frontend && npm install`
Expected: completes without error, creates `frontend/node_modules/`.

- [ ] **Step 2: Create `InsightCard.tsx`**

```tsx
"use client";

import React, { useState } from "react";
import {
  Sparkles,
  Table2,
  Terminal,
  Lightbulb,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
} from "lucide-react";

export interface Insight {
  question: string;
  executiveSummary: string;
  confidence: {
    score: number;
    rationale: string;
    sample_size_component?: number;
    effect_size_component?: number;
    known_issue_component?: number;
    cut_consistency_component?: number;
  };
  knownIssueMatch: boolean;
  matchedKnownIssue: string;
  cuts: Record<string, Array<Record<string, any>>>;
  views: {
    metric_deltas: Array<{ metric: string; baseline: string; observed: string; delta: string; impact: string }>;
  };
  sqlQueries: string[];
  specId: string;
  traceId: string;
  traceUrl: string;
}

function confidenceTier(score: number): { color: "emerald" | "amber" | "rose"; label: string } {
  if (score >= 0.8) return { color: "emerald", label: "High confidence" };
  if (score >= 0.5) return { color: "amber", label: "Moderate confidence" };
  return { color: "rose", label: "Low confidence" };
}

const TIER_CLASSES = {
  emerald: {
    bar: "bg-emerald-500",
    badgeBg: "bg-emerald-500/10",
    badgeText: "text-emerald-400",
    badgeBorder: "border-emerald-500/30",
  },
  amber: {
    bar: "bg-amber-500",
    badgeBg: "bg-amber-500/10",
    badgeText: "text-amber-400",
    badgeBorder: "border-amber-500/30",
  },
  rose: {
    bar: "bg-rose-500",
    badgeBg: "bg-rose-500/10",
    badgeText: "text-rose-400",
    badgeBorder: "border-rose-500/30",
  },
} as const;

function SectionEyebrow({ icon: Icon, children }: { icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-2">
      <Icon className="w-3.5 h-3.5" />
      <span>{children}</span>
    </div>
  );
}

export default function InsightCard({ insight }: { insight: Insight }) {
  const tier = confidenceTier(insight.confidence?.score ?? 0);
  const tierClasses = TIER_CLASSES[tier.color];
  const [sqlOpen, setSqlOpen] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const handleCopySql = (idx: number, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const cutEntries = Object.entries(insight.cuts || {}).filter(([, rows]) => rows && rows.length > 0);
  const metricDeltas = insight.views?.metric_deltas || [];
  const hasFacts = cutEntries.length > 0 || metricDeltas.length > 0;
  const sqlQueries = insight.sqlQueries || [];

  return (
    <div className="relative rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${tierClasses.bar}`} />
      <div className="pl-5 pr-4 py-4 space-y-4">
        <div>
          <div className="flex items-start justify-between gap-3">
            <SectionEyebrow icon={Sparkles}>Overall Summary</SectionEyebrow>
            <span
              className={`shrink-0 px-2 py-0.5 rounded-md border text-[10px] font-semibold ${tierClasses.badgeBg} ${tierClasses.badgeText} ${tierClasses.badgeBorder}`}
              title={tier.label}
            >
              {"●"} {(insight.confidence?.score ?? 0).toFixed(2)}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-slate-200">{insight.executiveSummary}</p>
        </div>

        {hasFacts && (
          <div className="border-t border-slate-800 pt-4">
            <SectionEyebrow icon={Table2}>Facts</SectionEyebrow>
            {metricDeltas.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                {metricDeltas.map((m, idx) => (
                  <div key={idx} className="rounded-lg bg-slate-950/60 border border-slate-800 px-2.5 py-2">
                    <div className="text-[10px] text-slate-500 truncate">{m.metric}</div>
                    <div className="text-sm font-semibold text-slate-100">{m.observed}</div>
                    <div className="text-[10px] text-slate-400">{m.delta}</div>
                  </div>
                ))}
              </div>
            )}
            {cutEntries.map(([dim, rows]) => {
              const columns = Object.keys(rows[0] || {});
              return (
                <div key={dim} className="mb-3 last:mb-0 overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-950/60 text-slate-400">
                        <th className="text-left px-2.5 py-1.5 font-medium">{dim}</th>
                        {columns
                          .filter((c) => c !== dim)
                          .map((c) => (
                            <th key={c} className="text-right px-2.5 py-1.5 font-medium">
                              {c}
                            </th>
                          ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 8).map((row, ridx) => (
                        <tr key={ridx} className="border-t border-slate-800/80 text-slate-300">
                          <td className="px-2.5 py-1.5">{String(row[dim] ?? "")}</td>
                          {columns
                            .filter((c) => c !== dim)
                            .map((c) => (
                              <td key={c} className="text-right px-2.5 py-1.5 tabular-nums">
                                {String(row[c] ?? "")}
                              </td>
                            ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}

        {sqlQueries.length > 0 && (
          <div className="border-t border-slate-800 pt-4">
            <button
              onClick={() => setSqlOpen((v) => !v)}
              className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-2 hover:text-slate-300 transition-colors"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>
                SQL ({sqlQueries.length} {sqlQueries.length === 1 ? "query" : "queries"})
              </span>
              {sqlOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </button>
            {sqlOpen && (
              <div className="space-y-2">
                {sqlQueries.map((sql, idx) => (
                  <div key={idx} className="group relative rounded-lg bg-slate-950 border border-slate-800 px-3 py-2.5">
                    <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all pr-8">{sql}</pre>
                    <button
                      onClick={() => handleCopySql(idx, sql)}
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-slate-200"
                    >
                      {copiedIdx === idx ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="border-t border-slate-800 pt-4">
          <SectionEyebrow icon={Lightbulb}>Why this is right</SectionEyebrow>
          <p className="text-xs leading-relaxed text-slate-300">{insight.confidence?.rationale}</p>
          {insight.knownIssueMatch && insight.matchedKnownIssue && (
            <div className="mt-2 px-2.5 py-1.5 rounded-md bg-blue-500/10 border border-blue-500/30 text-[11px] text-blue-300">
              {"🔗"} {insight.matchedKnownIssue}
            </div>
          )}
        </div>

        {insight.traceUrl && (
          <div className="border-t border-slate-800 pt-4 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <ExternalLink className="w-3.5 h-3.5" />
              <span className="uppercase tracking-wide font-semibold">Trace</span>
              <span className="font-mono text-slate-600">{"·"} {insight.traceId?.slice(0, 12)}</span>
            </div>
            <a
              href={insight.traceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] font-medium text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              View <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `InsightCardSkeleton.tsx`**

```tsx
export default function InsightCardSkeleton() {
  return (
    <div className="relative rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden animate-pulse">
      <div className="absolute left-0 top-0 bottom-0 w-1 bg-slate-700" />
      <div className="pl-5 pr-4 py-4 space-y-4">
        <div>
          <div className="h-2.5 w-24 bg-slate-800 rounded mb-2" />
          <div className="h-3 w-full bg-slate-800 rounded mb-1.5" />
          <div className="h-3 w-4/5 bg-slate-800 rounded" />
        </div>
        <div className="border-t border-slate-800 pt-4">
          <div className="h-2.5 w-16 bg-slate-800 rounded mb-2" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="h-12 bg-slate-800/60 rounded-lg" />
            <div className="h-12 bg-slate-800/60 rounded-lg" />
            <div className="h-12 bg-slate-800/60 rounded-lg" />
            <div className="h-12 bg-slate-800/60 rounded-lg" />
          </div>
        </div>
        <div className="border-t border-slate-800 pt-4">
          <div className="h-2.5 w-20 bg-slate-800 rounded mb-2" />
          <div className="h-3 w-3/4 bg-slate-800 rounded" />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create a temporary preview route to visually verify both components**

Create `frontend/app/dev-insight-preview/page.tsx`:

```tsx
import InsightCard, { Insight } from "../components/InsightCard";
import InsightCardSkeleton from "../components/InsightCardSkeleton";

const SAMPLE_INSIGHT: Insight = {
  question: "conversion on express checkout looks off this month — what's going on?",
  executiveSummary:
    "iOS users in the UAE are failing at the OTP step specifically, starting the day after K1 was documented. Conversion dropped 15.2 percentage points, concentrated 78% in ios x AE.",
  confidence: {
    score: 0.87,
    rationale: "Large sample (5,507 events), large effect (-15.2pp), documented known-issue match, consistent across five cuts.",
  },
  knownIssueMatch: true,
  matchedKnownIssue: "K1 — iOS WebKit OTP autofill regression, logged 2026-03-11",
  cuts: {
    device_type: [
      { device_type: "ios", events: 2302, users: 690 },
      { device_type: "android", events: 1855, users: 540 },
      { device_type: "web-user-b2c", events: 1043, users: 310 },
    ],
  },
  views: {
    metric_deltas: [
      { metric: "Baseline (Feb)", baseline: "N/A", observed: "62.4%", delta: "", impact: "" },
      { metric: "Observed (Mar)", baseline: "N/A", observed: "47.2%", delta: "-15.2pp", impact: "" },
      { metric: "Sample", baseline: "N/A", observed: "5,507 events", delta: "1,650 users", impact: "" },
    ],
  },
  sqlQueries: [
    "SELECT device_type, count() AS events, uniq(user_id) AS users FROM express_checkout WHERE event = 'express_payment_confirmed' GROUP BY device_type ORDER BY events DESC",
    "SELECT toDate(timestamp) AS day, countIf(otp_success = 1) / count() AS conv FROM express_checkout GROUP BY day ORDER BY day",
  ],
  specId: "01_express_checkout",
  traceId: "abc123def456",
  traceUrl: "https://us.cloud.langfuse.com/trace/abc123def456",
};

export default function DevInsightPreview() {
  return (
    <div className="min-h-screen bg-[#090d16] p-8 space-y-6 max-w-2xl mx-auto">
      <InsightCard insight={SAMPLE_INSIGHT} />
      <InsightCardSkeleton />
    </div>
  );
}
```

- [ ] **Step 5: Type-check and build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors (this compiles `dev-insight-preview` too, which is fine — it gets deleted in Step 8 before this task's diff is committed).

- [ ] **Step 6: Start the dev server and visually verify with a real browser**

Run in the background: `cd frontend && npm run dev` (starts on `http://localhost:3000`)

Use the `mcp__puppeteer__puppeteer_navigate` tool to open `http://localhost:3000/dev-insight-preview`, then `mcp__puppeteer__puppeteer_screenshot` to capture it. Verify visually:
- The left accent bar is emerald (score 0.87 ≥ 0.8).
- All 5 sections render: Overall Summary with the confidence badge, Facts with 3 stat tiles + the device_type table, SQL section collapsed by default (click it via `mcp__puppeteer__puppeteer_click` and screenshot again to confirm it expands and shows both queries with monospace formatting), Why This Is Right with the known-issue badge, Trace with a working "View →" link.
- The skeleton below it shows shimmer blocks in the same layout shape, not the real content.
- No layout overflow, no console errors (check via `mcp__puppeteer__puppeteer_evaluate` running `window.__consoleErrors || []` is not required — visually confirm no broken/unstyled elements instead).

Stop the dev server process when done.

- [ ] **Step 7: Delete the temporary preview route**

```bash
rm -rf frontend/app/dev-insight-preview
```

- [ ] **Step 8: Confirm the final diff is component-only**

Run: `cd frontend && git status --short`
Expected: only `frontend/app/components/InsightCard.tsx` and `frontend/app/components/InsightCardSkeleton.tsx` show as new/untracked files (plus `node_modules/` and `.next/`, which are gitignored — confirm via `git status --short` showing no `node_modules` or `.next` entries; if they show up, check `frontend/.gitignore` covers them before committing).

- [ ] **Step 9: Commit**

```bash
git add frontend/app/components/InsightCard.tsx frontend/app/components/InsightCardSkeleton.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add InsightCard and InsightCardSkeleton components

Five-section presentational card (Summary/Facts/SQL/Reasoning/Trace
link) for CUJ2 analyst answers, with a confidence-tier-colored accent
bar as the signature element. Verified in a real browser via a
temporary preview route (removed before this commit) with Puppeteer.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Frontend — wire `page.tsx` to the Insight Card

**Files:**
- Create: `frontend/app/api/analyze/query/route.ts` (Next.js proxy to the backend's `/api/analyze/query`, mirroring the existing `frontend/app/api/chat/route.ts` pattern)
- Create: `frontend/app/components/MarkdownBubble.tsx` (extracted from the existing inline JSX in `page.tsx`)
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `Insight` type and `InsightCard` (Task 3), `InsightCardSkeleton` (Task 3).
- Produces: `MarkdownBubble.tsx` exports `export default function MarkdownBubble({ msg, isUser, copiedId, onCopy }: { msg: { id: string; role: "user"|"assistant"; content: string; timestamp: string }; isUser: boolean; copiedId: string | null; onCopy: (id: string, text: string) => void }): JSX.Element`.

- [ ] **Step 1: Create the Next.js proxy route**

The design doc's frontend architecture has analyst mode calling `/api/analyze/query` directly — but that's the *backend* FastAPI route. The Next.js app needs its own API route at that same path to forward the request server-side, exactly like `frontend/app/api/chat/route.ts` already does for `/v1/chat/completions`. Without this file, `fetch("/api/analyze/query")` from the browser would 404 against Next.js's own (nonexistent) route.

Create `frontend/app/api/analyze/query/route.ts`:

```ts
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

export async function POST(req: NextRequest) {
  try {
    const { question, spec_id } = await req.json();

    const backendUrl =
      process.env.INSIGHTMESH_BACKEND_URL ||
      "https://insightmesh-backend.onrender.com";

    const response = await fetch(`${backendUrl}/api/analyze/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        spec_id: spec_id || "chat",
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("API analyze proxy error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to contact InsightMesh backend" },
      { status: 500 }
    );
  }
}
```

- [ ] **Step 2: Extract `MarkdownBubble.tsx`**

Create `frontend/app/components/MarkdownBubble.tsx` with the markdown-bubble JSX currently inline in `page.tsx`'s message-rendering loop:

```tsx
"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import { Copy, Check } from "lucide-react";

interface MarkdownBubbleMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export default function MarkdownBubble({
  msg,
  isUser,
  copiedId,
  onCopy,
}: {
  msg: MarkdownBubbleMessage;
  isUser: boolean;
  copiedId: string | null;
  onCopy: (id: string, text: string) => void;
}) {
  return (
    <div
      className={`group relative max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
        isUser
          ? "bg-blue-600 text-white rounded-br-none"
          : "bg-slate-900 border border-slate-800 text-slate-200 rounded-bl-none"
      }`}
    >
      {!isUser ? (
        <div className="prose prose-invert prose-sm max-w-none prose-pre:bg-slate-950 prose-pre:border prose-pre:border-slate-800">
          <ReactMarkdown>{msg.content}</ReactMarkdown>
        </div>
      ) : (
        <p className="whitespace-pre-wrap">{msg.content}</p>
      )}

      <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-slate-400">
        <span>{msg.timestamp}</span>
        {!isUser && msg.content && (
          <button
            onClick={() => onCopy(msg.id, msg.content)}
            className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 hover:text-slate-200"
          >
            {copiedId === msg.id ? (
              <Check className="w-3 h-3 text-emerald-400" />
            ) : (
              <Copy className="w-3 h-3" />
            )}
            <span>{copiedId === msg.id ? "Copied" : "Copy"}</span>
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Replace `frontend/app/page.tsx` with the wired version**

Replace the entire contents of `frontend/app/page.tsx` with:

```tsx
"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Send,
  Sparkles,
  RefreshCw,
  Bot,
  User,
  Wrench,
  LineChart,
} from "lucide-react";
import MarkdownBubble from "./components/MarkdownBubble";
import InsightCard, { Insight } from "./components/InsightCard";
import InsightCardSkeleton from "./components/InsightCardSkeleton";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  insight?: Insight;
  timestamp: string;
}

const NON_ANALYTICAL_SPEC_IDS = new Set(["conversational", "abusive_deescalation", "out_of_scope", "none"]);

function mapInsightResponse(json: any): Insight {
  return {
    question: json.question ?? "",
    executiveSummary: json.executive_summary ?? "",
    confidence: json.confidence ?? { score: 0, rationale: "" },
    knownIssueMatch: json.known_issue_match ?? false,
    matchedKnownIssue: json.matched_known_issue ?? "",
    cuts: json.cuts ?? {},
    views: json.views ?? { metric_deltas: [] },
    sqlQueries: json.sql_queries ?? [],
    specId: json.spec_id ?? "",
    traceId: json.trace_id ?? "",
    traceUrl: json.trace_url ?? "",
  };
}

const AGENT_MODELS = [
  {
    id: "atlys-instrumentation",
    name: "Atlys Instrumentation Engineer",
    cuj: "CUJ 1: Schema Ingestion & DDL",
    desc: "Infers ClickHouse schemas from specs, generates DDL, Materialized Views, and Context Diffs.",
    icon: Wrench,
    badgeColor: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  },
  {
    id: "atlys-analyst",
    name: "Atlys Product Analyst",
    cuj: "CUJ 2: ClickHouse Analytics",
    desc: "Answers natural language business questions, queries ClickHouse Cloud, and analyzes conversion funnels.",
    icon: LineChart,
    badgeColor: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  },
];

const SUGGESTIONS = [
  { text: "ingest 01_express_checkout", model: "atlys-instrumentation" },
  { text: "Show available specs and schema status", model: "atlys-instrumentation" },
  { text: "What is the checkout to payment completion conversion rate?", model: "atlys-analyst" },
  { text: "Show hourly payment drop-off by provider", model: "atlys-analyst" },
];

export default function ChatPage() {
  const [selectedModel, setSelectedModel] = useState("atlys-instrumentation");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "👋 **Welcome to InsightMesh!**\n\nI am your autonomous **ClickHouse & Event Analytics Intelligence Engine**.\n\n* Select **Atlys Instrumentation Engineer** to infer schemas, generate ClickHouse DDL, and inspect context diffs.\n* Select **Atlys Product Analyst** to run natural language SQL analytics and conversion funnel queries.\n\nHow can I help you today?",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleSend = async (textToSend?: string) => {
    const query = textToSend || input.trim();
    if (!query || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput("");
    setIsLoading(true);

    const assistantMsgId = `assistant-${Date.now()}`;
    const placeholderAssistant: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages([...newMessages, placeholderAssistant]);

    if (selectedModel === "atlys-analyst") {
      try {
        const res = await fetch("/api/analyze/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: query, spec_id: "chat" }),
        });

        if (!res.ok) {
          throw new Error(`Server returned ${res.status}`);
        }

        const json = await res.json();
        const insight = mapInsightResponse(json);

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, content: json.answer_md || insight.executiveSummary, insight }
              : msg
          )
        );
      } catch (err: any) {
        console.error("Error fetching analyst insight:", err);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId
              ? {
                  ...msg,
                  content: `⚠️ **Error connecting to InsightMesh backend:** ${err.message}\n\nPlease check that the backend service is reachable.`,
                }
              : msg
          )
        );
      } finally {
        setIsLoading(false);
      }
      return;
    }

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: selectedModel,
          messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      if (!res.body) {
        throw new Error("No response body received");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[DONE]") continue;
            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta?.content || "";
              accumulated += delta;
            } catch {
              accumulated += data;
            }
          } else if (line.trim().length > 0 && !line.startsWith(":")) {
            accumulated += line;
          }
        }

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMsgId ? { ...msg, content: accumulated } : msg
          )
        );
      }
    } catch (err: any) {
      console.error("Error streaming chat:", err);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content:
                  msg.content ||
                  `⚠️ **Error connecting to InsightMesh backend:** ${err.message}\n\nPlease check that the backend service is reachable.`,
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const activeAgent = AGENT_MODELS.find((m) => m.id === selectedModel)!;
  const ActiveIcon = activeAgent.icon;

  return (
    <div className="flex flex-col h-screen max-w-5xl mx-auto w-full px-4 sm:px-6">
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between py-4 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 shadow-lg shadow-blue-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              InsightMesh
            </h1>
            <p className="text-xs text-slate-400">Atlys Event Analytics & Schema Engine</p>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:flex-initial">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full sm:w-64 bg-slate-900 border border-slate-700 hover:border-slate-600 rounded-lg px-3 py-2 text-xs font-medium text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
            >
              {AGENT_MODELS.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>ClickHouse Online</span>
          </div>
        </div>
      </header>

      <div className="py-2.5 px-3.5 my-3 rounded-lg bg-slate-900/60 border border-slate-800/80 flex items-center justify-between text-xs text-slate-300">
        <div className="flex items-center gap-2">
          <ActiveIcon className="w-4 h-4 text-blue-400" />
          <span className="font-semibold text-slate-200">{activeAgent.name}</span>
          <span className="hidden md:inline text-slate-500">•</span>
          <span className="hidden md:inline text-slate-400">{activeAgent.desc}</span>
        </div>
        <span className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold ${activeAgent.badgeColor}`}>
          {activeAgent.cuj}
        </span>
      </div>

      <main className="flex-1 overflow-y-auto space-y-4 py-2 pr-1">
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          const showInsightCard =
            !isUser && msg.insight && !NON_ANALYTICAL_SPEC_IDS.has(msg.insight.specId);
          return (
            <div
              key={msg.id}
              className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
            >
              {!isUser && (
                <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot className="w-4 h-4 text-blue-400" />
                </div>
              )}

              {showInsightCard ? (
                <div className="max-w-[85%] w-full">
                  <InsightCard insight={msg.insight!} />
                  <div className="mt-1 text-[10px] text-slate-500">{msg.timestamp}</div>
                </div>
              ) : (
                <MarkdownBubble msg={msg} isUser={isUser} copiedId={copiedId} onCopy={handleCopy} />
              )}

              {isUser && (
                <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User className="w-4 h-4 text-slate-300" />
                </div>
              )}
            </div>
          );
        })}

        {isLoading &&
          (selectedModel === "atlys-analyst" ? (
            <div className="flex gap-3 items-start">
              <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
              </div>
              <div className="max-w-[85%] w-full">
                <InsightCardSkeleton />
              </div>
            </div>
          ) : (
            <div className="flex gap-3 items-center text-xs text-slate-400 py-2">
              <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
                <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
              </div>
              <span>Agent is consulting ClickHouse & Gemini 3...</span>
            </div>
          ))}

        <div ref={messagesEndRef} />
      </main>

      {messages.length <= 2 && (
        <div className="py-2">
          <p className="text-[11px] text-slate-400 font-medium mb-1.5">Suggested Prompts:</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {SUGGESTIONS.map((s, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setSelectedModel(s.model);
                  handleSend(s.text);
                }}
                className="text-left px-3 py-2 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-800/80 hover:border-slate-700 text-xs text-slate-300 transition-all flex items-center justify-between"
              >
                <span className="truncate">{s.text}</span>
                <span className="text-[10px] text-slate-500 ml-2 whitespace-nowrap">
                  {s.model === "atlys-instrumentation" ? "CUJ 1" : "CUJ 2"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <footer className="py-3 border-t border-slate-800">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="relative flex items-center"
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${activeAgent.name} (Press Enter to send)...`}
            className="w-full bg-slate-900 border border-slate-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 resize-none pr-12 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
        <p className="text-[10px] text-center text-slate-500 mt-2">
          InsightMesh • Powered by ClickHouse Cloud, chDB, Gemini 3 Flash & CrewAI
        </p>
      </footer>
    </div>
  );
}
```

Note what changed vs the original: `ReactMarkdown`, `Database`, `Cpu`, `Copy`, `Check` imports removed (moved into `MarkdownBubble.tsx`, or were dead — `Database`/`Cpu` were imported but never used in the original file); `MarkdownBubble`/`InsightCard`/`InsightCardSkeleton` imports added; `Message.insight` field added; `NON_ANALYTICAL_SPEC_IDS` and `mapInsightResponse` added; `handleSend` gains the analyst-mode branch (returns early after the JSON fetch, before the instrumentation-mode SSE code); the message-rendering loop picks `InsightCard` vs `MarkdownBubble` per message; the loading indicator picks skeleton vs spinner based on `selectedModel`.

- [ ] **Step 4: Type-check and build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/api/analyze/query/route.ts frontend/app/components/MarkdownBubble.tsx frontend/app/page.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): wire analyst mode to the Insight Card

Analyst-mode messages now call the new /api/analyze/query proxy route
(forwarding to the backend's existing REST endpoint) instead of
streaming markdown from /v1/chat/completions, and render the response
through InsightCard. Instrumentation-agent mode is unchanged.
Extracted the existing markdown-bubble JSX into MarkdownBubble so both
renderers are selected between per-message. Non-analytical replies
(greetings, out-of-scope, etc.) keep rendering as plain markdown via
the spec_id sentinel check.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: End-to-end verification — real backend + real browser

**Files:** none (verification only; may produce a fix commit if something's broken).

**Interfaces:** none — this task exercises Tasks 1-4's combined output.

- [ ] **Step 1: Start the backend**

Run in the background from the repo root: `.venv/bin/python -c "from atlys_agentic.run_chat import start_service; start_service(port=8008)"`
Expected: server starts, `curl http://localhost:8008/healthz` returns `{"status":"ok"}`.

- [ ] **Step 2: Start the frontend pointed at the local backend**

Run in the background from `frontend/`: `INSIGHTMESH_BACKEND_URL=http://localhost:8008 npm run dev`
Expected: server starts on `http://localhost:3000`.

- [ ] **Step 3: Golden path — analyst question renders an Insight Card**

Use `mcp__puppeteer__puppeteer_navigate` to open `http://localhost:3000`. Use `mcp__puppeteer__puppeteer_click` to select "Atlys Product Analyst" from the model dropdown (or `mcp__puppeteer__puppeteer_select` if it's a native `<select>`). Use `mcp__puppeteer__puppeteer_fill` to type a question into the textarea (e.g. "What is the checkout to payment completion conversion rate?" — one of the existing `SUGGESTIONS`), then submit.

Wait for the response (the backend call may take a few seconds — it's a real ClickHouse/chDB round trip). Use `mcp__puppeteer__puppeteer_screenshot` to capture the result.

Verify: an `InsightCard` rendered (not a plain markdown bubble) with a non-empty Overall Summary, a confidence badge, and (if the backend returned SQL queries) a working SQL section. This is calling the real backend with real credentials already configured in `src/atlys_agentic/config/.env` — if the answer comes back with empty `cuts`/`sql_queries` (e.g. ClickHouse Cloud unreachable in this sandbox), that's fine as long as the *card renders correctly* around whatever data came back — the point of this check is the frontend plumbing, not backend data quality.

- [ ] **Step 4: Edge case — non-analytical reply stays plain markdown**

Send a greeting (e.g. "hi") in analyst mode via the same flow. Screenshot the result. Verify: a plain `MarkdownBubble` renders (not an `InsightCard`) — confirms the `spec_id` sentinel check in `page.tsx` correctly routes greetings away from the card.

- [ ] **Step 5: Edge case — instrumentation mode is unaffected**

Switch to "Atlys Instrumentation Engineer", send "what specs are available?". Screenshot the result. Verify: the response streams in as before (markdown bubble, not an Insight Card, not calling `/api/analyze/query`) — confirms Task 4's changes didn't regress CUJ 1.

- [ ] **Step 6: If anything is broken, fix it now**

If any of Steps 3-5 reveal a bug (card doesn't render, wrong branch taken, console error, visual glitch), fix it directly in the relevant file from Tasks 3/4, re-run the affected step to confirm, and note the fix in this task's commit message. If everything works, there's nothing to fix — proceed to Step 7.

- [ ] **Step 7: Stop both servers**

Kill the backend and frontend dev processes started in Steps 1-2.

- [ ] **Step 8: Run the full backend test suite one more time**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: same result as the end of Task 2 — 5 pre-existing failures, all others (including the 2 new tests from Tasks 1-2) passing.

- [ ] **Step 9: Commit (only if Step 6 produced changes)**

```bash
git add -A
git commit -m "$(cat <<'EOF'
fix: address issues found in end-to-end browser verification

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

If Step 6 found nothing to fix, skip this commit — there's nothing new to add.

---

## Self-review notes

- **Spec coverage:** design doc §3 (backend) → Tasks 1-2. §4 (frontend architecture, including the `Insight`/`Message` types and `mapInsightResponse`) → Tasks 3-4. §5 (component/visual design, all 5 sections, signature accent bar, icons) → Task 3. §6 (data flow/edge cases: loading skeleton, non-analytical sentinel check, error fallback, defensive rendering, copy-to-clipboard) → Tasks 3-4, verified live in Task 5. §7 deliverables → all 5 files listed there are created/modified across Tasks 1-4, plus the corrected addition (the Next.js proxy route the design doc didn't spell out, called out explicitly in Task 4 Step 1 and in Global Constraints). §8 out-of-scope items (CUJ1 UI, charts, AI SDK, locked CUJ2 design fields) — untouched by any task, confirmed via Task 5 Step 5's instrumentation-mode regression check.
- **Placeholder scan:** no TBD/TODO; every step has runnable code, exact commands, or (Task 5) concrete Puppeteer tool calls with specific things to verify.
- **Type/interface consistency:** `Insight` is defined once in `InsightCard.tsx` (Task 3) and imported by `page.tsx` (Task 4) rather than redefined — `mapInsightResponse`'s return shape matches the `Insight` interface field-for-field. `MarkdownBubble`'s prop shape (`msg`/`isUser`/`copiedId`/`onCopy`) matches exactly how `page.tsx` calls it in Task 4 Step 3. The backend's `trace_url` field name (snake_case, Task 1-2) is correctly mapped to `traceUrl` (camelCase) in `mapInsightResponse` (Task 4).
