# CUJ 2 — What the Analyst Does (Plain-Language Summary)

This is a short, plain-language description of the Atlys Product Analyst, written to be
quoted directly to a user who asks what this system does or how it works. It describes the
system's *actual current behavior*, not aspirational or planned capabilities. For the full
locked design specification, engineers should read `docs/CUJ2.md`.

## What it is

The Atlys Product Analyst is a chat-based analytics assistant. A product manager asks a
natural-language question about product telemetry — a conversion funnel, a drop-off, a
segment comparison — and the Analyst investigates it directly against the live ClickHouse
event data and returns a plain-English diagnosis with a confidence score and a trace link.

## What it does not do

The Analyst does not design database schemas, generate DDL, or run data ingestion. Adding a
new feature's telemetry to the system is a separate job, owned by a different model in this
same chat interface: the **Instrumentation Engineer** (`atlys-instrumentation`). If a question
is about ingesting a spec, proposing a table, or ClickHouse schema design, the right place to
ask it is that model, not this one.

The Analyst also does not run arbitrary SQL on request, and does not fabricate a number when
the data cannot answer the question — it says so plainly instead.

## How it investigates a question

1. **Pull relevant context.** Before looking at any numbers, the Analyst checks its business
   context layer for known issues and metric definitions relevant to the question — so a
   drop that matches a previously logged regression is recognized as such, not treated as new.
2. **Resolve the feature domain.** It works out which feature and which ClickHouse table the
   question is actually about (express checkout, group/family applications, abandoned
   checkout recovery, multi-currency pricing, and so on).
3. **Run the segment cuts.** It aggregates the relevant event data inside ClickHouse — never
   pulling raw rows into the conversation — cut by segment dimensions that matter for
   diagnosis, at minimum device type, country, and destination.
4. **Check for a known-issue match.** If the pattern in the data lines up with something
   already logged in the business context layer, the answer says so explicitly instead of
   re-diagnosing from scratch.
5. **Score confidence.** Every answer carries a confidence score, based on sample size,
   effect size, and whether a known issue was matched — not a flat, unexplained number.
6. **Write the answer.** The final response states the headline finding, where in the data it
   concentrates, the likely mechanism, and a concrete next step.

## What it's good at answering

- Conversion and funnel drop-off diagnosis ("is there an iOS OTP drop on Express Checkout
  during verification?")
- Segment comparisons (by device, by country, by destination)
- Whether a pattern matches a previously known issue, or looks new
- Confidence-scored, PM-actionable summaries rather than raw charts

## Traceability

Every answer the Analyst gives links to a Langfuse trace, so the reasoning chain behind a
diagnosis — which context was pulled, which cuts were run, which known issue (if any) was
matched — can be inspected, not just trusted.
