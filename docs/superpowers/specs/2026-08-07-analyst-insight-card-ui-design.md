# Analyst Insight Card — structured UI for CUJ 2 answers

**Status:** approved. **Branch:** `feat/analyst-insight-card`.

## 1. Problem

The Vercel frontend (`frontend/`) talks to the backend exclusively through `/v1/chat/completions`
and renders every reply — instrumentation-agent proposals and analyst-agent insights alike — as a
single markdown bubble. For analyst-mode (CUJ 2) answers this throws away almost everything the
backend already computes: `analysis_flow.run()` returns `executive_summary`, `confidence` (with a
4-component breakdown), `cuts` (per-dimension breakdowns), `views` (metric deltas, trend, segment
waterfall), `sql_queries`, and `trace_id` — `run_chat.py`'s `/v1/chat/completions` handler keeps
only `answer_md` (`run_chat.py:226`) and discards the rest.

There's also no real streaming happening today: `analysis_flow.run()` computes the complete answer
server-side, then `/v1/chat/completions` chunks the finished string line-by-line over SSE
(`run_chat.py:260-291`) to imitate token streaming. The "streaming" illusion is free to give up.

Goal: render analyst answers as a structured card — Overall Summary, SQL, Facts, Reasoning ("why
this is right"), and a Langfuse trace link — as separate, purpose-built components instead of one
markdown blob, using data the backend already produces.

## 2. Decision: single structured JSON response for analyst mode

Analyst-mode (`selectedModel === "atlys-analyst"`) messages call the existing
`/api/analyze/query` REST endpoint (`run_chat.py:132-150`) instead of `/v1/chat/completions`.
That endpoint already returns every field the card needs except one (`trace_url` — see §3).
Instrumentation-agent mode (CUJ 1, HITL proposal/approve flow) is untouched — it stays on
`/v1/chat/completions`'s text stream, since its two-turn approval state machine is inherently
conversational and already works.

Rejected alternatives: the Vercel AI SDK's data-stream protocol (real capability, but a bigger
rework — new dependency, backend must speak the AI SDK's part-stream format instead of plain
OpenAI-style SSE — not justified when nothing in this backend does real token streaming today);
embedding a JSON blob inside the existing SSE text stream (keeps the fake-streaming illusion and
adds custom parsing for no benefit over just calling the REST endpoint directly).

## 3. Backend changes (small, additive)

`analysis_flow.run()`'s return dict (`flows/analysis_flow.py:671-683`) gains one field:

```python
"trace_url": tracing.trace_url() or "",
```

Captured the same way `ingestion_flow.generate_proposal()` already does it (`ingestion_flow.py:556`)
— read while the trace span is still active via `tracing.trace()`'s context manager, since the
trace id is unavailable once the block exits (see `tracing.py` module docstring).

`/api/analyze/query` (`run_chat.py:132-150`) adds `"trace_url": result.get("trace_url", "")` to its
response dict. `executive_summary`, `confidence`, `cuts`, `views`, `sql_queries`, `trace_id`
already flow through unchanged.

`spec_id` needed an actual fix, not just a pass-through: the endpoint was previously echoing back
`req.spec_id` (the caller's own value) instead of `result.get("spec_id", req.spec_id)` (the
backend's real classification from `analysis_flow.run()` — `"conversational"`,
`"abusive_deescalation"`, `"out_of_scope"`, `"none"`, or a real spec_id). Discovered during final
review: since the frontend always sends `spec_id: "chat"` (see §4), the bug meant every response
echoed `"chat"` back regardless of what the backend actually classified the question as — silently
breaking the non-analytical-reply routing in §6, which depends on reading the backend's
classification out of `insight.specId`.

## 4. Frontend architecture

`frontend/app/page.tsx`'s `Message` type gains an optional `insight` field:

```ts
interface Insight {
  question: string;
  executiveSummary: string;
  confidence: {
    score: number;
    rationale: string;
    sample_size_component: number;
    effect_size_component: number;
    known_issue_component: number;
    cut_consistency_component: number;
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

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;       // user messages, and instrumentation-mode markdown
  insight?: Insight;      // present only for analyst-mode analytical answers
  timestamp: string;
}
```

`handleSend` branches on `selectedModel`: instrumentation mode keeps the existing SSE-consuming
path unchanged; analyst mode does a plain `fetch("/api/analyze/query", { method: "POST", body:
{ question, spec_id: "chat" } })`, awaits the JSON body, and sets `insight` on the placeholder
message (converting the response's `snake_case` keys to the `Insight` type's `camelCase` — a
one-line mapping function, not a library).

The browser's `fetch("/api/analyze/query")` call needs a Next.js route to land on — that path only
exists on the FastAPI backend, not on the Next.js app. `frontend/app/api/analyze/query/route.ts`
(new file) is a thin proxy that forwards `question` to `${INSIGHTMESH_BACKEND_URL}/api/analyze/query`
with a hardcoded `spec_id: "chat"` (the only value the browser ever sends), mirroring the existing
`frontend/app/api/chat/route.ts` proxy pattern used by instrumentation mode.

New file `frontend/app/components/InsightCard.tsx` — pure presentational component, `{ insight:
Insight }` props, no data fetching of its own. `page.tsx`'s message-rendering loop checks
`msg.insight` before falling back to the existing markdown-bubble rendering: `msg.insight &&
!NON_ANALYTICAL_SPEC_IDS.has(msg.insight.specId) ? <InsightCard insight={msg.insight} /> :
<MarkdownBubble ... />` (extracting the current inline markdown-bubble JSX into its own
`MarkdownBubble` component alongside `InsightCard`, since `page.tsx` is already sizeable and both
components are now selected between rather than the bubble being the only path).

## 5. Component & visual design

Extends the app's existing visual language (dark slate, `bg-slate-900`/`border-slate-800`,
blue-indigo gradient accents, `text-[10px] uppercase tracking-wide text-slate-500` eyebrow labels
already used for the `CUJ 1`/`CUJ 2` badges) rather than introducing a new palette.

**Signature element:** a left-edge accent bar spanning the card's full height, colored by
confidence tier — `bg-emerald-500` (score ≥ 0.8), `bg-amber-500` (0.5–0.8), `bg-rose-500` (< 0.5).
Lets someone scanning a long conversation eyeball insight strength without reading text — grounded
in the actual subject (confidence-scored analytics findings), not decorative.

**Sections, top to bottom:**

1. **Overall Summary** — `Sparkles` icon eyebrow, `executiveSummary` text, confidence score badge
   (`●0.87`) top-right in the tier color.
2. **Facts** — stat tiles row from `views.metric_deltas` (metric/observed/delta), then a per-cut
   table from `cuts` (one table per dimension key present, columns inferred from the row shape).
   Hidden entirely if both `views.metric_deltas` and `cuts` are empty.
3. **SQL** — `Terminal` icon eyebrow, collapsible (`▶ SQL (N queries)` collapsed by default —
   these are diagnostic detail, not the headline), one `font-mono bg-slate-950` block per query
   in `sqlQueries`, each with a copy button (reusing the existing `handleCopy` pattern from
   `page.tsx`). Hidden if `sqlQueries` is empty.
4. **Why this is right** — `Lightbulb` icon eyebrow, `confidence.rationale` text, plus a
   known-issue badge (`matchedKnownIssue`) when `knownIssueMatch` is true.
5. **Trace** — `ExternalLink` icon eyebrow, `traceId` shown as a short mono chip, `View →` button
   linking to `traceUrl` in a new tab. Hidden if `traceUrl` is empty (never links to nowhere).

No new dependencies — SQL rendering reuses the existing monospace/code-block styling pattern
already applied to markdown fenced code (`prose-pre:bg-slate-950 prose-pre:border
prose-pre:border-slate-800` in `page.tsx`), icons come from `lucide-react` (already a dependency,
same icon vocabulary as the existing `Wrench`/`LineChart` agent badges). No charting library —
Facts ships as tables/stat-tiles now; the component boundary (`InsightCard` reading directly from
`cuts`/`views.metric_deltas`) is chart-ready for a later pass without restructuring.

**Motion:** none added beyond what the app already has (message fade/scroll-in). The only
interactive moment is the SQL section's expand/collapse.

## 6. Data flow, edge cases, error handling

**Loading state.** Analyst mode is a single JSON fetch, not a growing stream, so the existing
"Agent is consulting ClickHouse & Gemini 3..." spinner line is replaced (for analyst mode only)
with a skeleton `InsightCard` — accent bar + shimmer blocks in the real layout's shape — so the
loading state previews what's coming rather than showing an unrelated indicator.

**Non-analytical replies stay plain markdown.** `analysis_flow.run()` returns sentinel `spec_id`
values for greetings/out-of-scope/empty input: `"conversational"`, `"abusive_deescalation"`,
`"out_of_scope"`, `"none"` (`flows/analysis_flow.py:596-638`). These have empty `cuts` and
near-zero `confidence` and would render as a mostly-empty card. Frontend checks `insight.specId`
against a `NON_ANALYTICAL_SPEC_IDS` set; matches render the existing markdown bubble using
`answer_md` (mapped into `content`) instead of `InsightCard`.

**Errors.** A failed `/api/analyze/query` call (network error, non-2xx) falls back to the existing
plain-bubble error message pattern already in `page.tsx`'s catch block — no new error UI, the
message simply never gets an `insight` and renders as an error bubble.

**Defensive rendering.** `InsightCard` treats every field as possibly absent: empty `sqlQueries`
hides the SQL section (not "0 queries"); empty `cuts` and empty `views.metric_deltas` together hide
Facts; missing `traceUrl` hides the trace button rather than linking nowhere; a missing/zero
confidence score still renders the badge (rose tier, "insufficient data" label) rather than
crashing on `undefined`.

**Copy-to-clipboard.** SQL section reuses `page.tsx`'s existing `handleCopy(id, text)` /
`copiedId` state, one button per query.

## 7. Deliverables

- `frontend/app/page.tsx` — `Message.insight` field, analyst-mode fetch branch in `handleSend`,
  extraction of `MarkdownBubble`, selection between `MarkdownBubble`/`InsightCard`, skeleton
  loading state for analyst mode.
- `frontend/app/components/InsightCard.tsx` — the 5-section card (new file).
- `frontend/app/components/InsightCardSkeleton.tsx` — loading placeholder matching the real
  layout (new file).
- `frontend/app/api/analyze/query/route.ts` — Next.js proxy route so the browser's
  `fetch("/api/analyze/query")` reaches the FastAPI backend; mirrors the existing
  `frontend/app/api/chat/route.ts` pattern (new file).
- `src/atlys_agentic/flows/analysis_flow.py` — add `trace_url` to `run()`'s return dict.
- `src/atlys_agentic/run_chat.py` — add `trace_url` to `/api/analyze/query`'s response dict, and
  fix `spec_id` to return `result.get("spec_id", req.spec_id)` (the backend's real classification)
  instead of echoing `req.spec_id` back unchanged.

## 8. Out of scope

- Instrumentation-agent (CUJ 1) UI — untouched, stays on the existing text-streaming chat endpoint.
- Charts/graphs for the Facts section — tables + stat tiles now (user decision); component
  boundary is chart-ready for a later pass.
- Vercel AI SDK adoption / real token streaming — rejected in §2, not justified by what the
  backend actually does today.
- The locked CUJ 2 design's richer answer shape (`docs/CUJ2.md` — denominator-conflict headline,
  concentration ratio, date coincidence, trend state, decline path) — the current
  `analysis_flow.run()` implementation doesn't produce these fields yet; this UI renders what the
  backend actually returns today. Extending `analysis_flow.run()` toward the locked design is a
  separate, backend-focused effort.
