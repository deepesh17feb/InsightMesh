# Atlys Agentic Analytics System

This package implements a CrewAI-based agentic analytics pipeline for the Atlys hackathon submission. The system combines instrumentation, context, and analytics agents operating on ClickHouse and chDB data stores. For the complete design documentation, see `final_wiby.md`.

The system provides two primary entrypoints:
- `run_ingestion.py --spec_dir specs/NN` — runs ingestion and analytics pipeline for a specific spec
- `run_chat.py` — launches the chat interface (deployed behind LibreChat)
