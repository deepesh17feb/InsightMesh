# Day-2 Unseen-Spec Runbook

1. Drop sealed files into `problem statment/specs/06_unseen/{spec.md, events.ndjson}`.
2. `cd src/atlys_agentic && python run_ingestion.py --spec_dir ../../problem\ statment/specs/06_unseen --table <name from spec>`
   — review the printed DDL/MV, type `APPROVE`.
3. Ask the PM question(s) from the spec via the LibreChat "Atlys Analyst" endpoint
   (`docker compose -f src/atlys_agentic/librechat/docker-compose.librechat.yml up -d`, backend already
   running via `uvicorn src.atlys_agentic.run_chat:app --port 8008`), or call
   `flows.analysis_flow.run(...)` directly from a Python shell.
4. Export the Langfuse trace: open the "Atlys Analyst" project, find the run tagged
   `06_unseen`, copy the trace URL, and `GET` the trace JSON via the Langfuse API.
5. `python src/atlys_agentic/assemble_submission.py --spec_id 06_unseen --ddl_file src/atlys_agentic/outputs/schemas/<table>.sql --insight_file src/atlys_agentic/outputs/insights/<question>.md --trace_file src/atlys_agentic/outputs/traces/<trace_id>.json`
6. Confirm `src/atlys_agentic/submission/06_unseen/{schema.sql, insight.md, trace.json}` all exist and are non-empty.
7. This exact sequence was already rehearsed end-to-end on `01_express_checkout` in
   `src/atlys_agentic/tests/test_e2e_rehearsal.py` — if Day 2 fails at any step, that test is the first
   thing to re-run to isolate whether it's an environment issue or a 6th-spec-specific one.
