# Critical User Journeys (CUJ) & Architecture

This document details the two Critical User Journeys implemented in the Atlys Agentic Analytics System:

- **CUJ 1**: Automated Feature Ingestion & Context Audit Pipeline
- **CUJ 2**: Analyst Query & Anomaly Detection Interface

---

## CUJ 1: Feature Ingestion & Context Audit Pipeline

### Purpose
Automates the transition from a product feature specification (`spec.md`) and raw event data (`events.ndjson`) to production ClickHouse tables and materialized views, with an interactive Human-in-the-Loop approval gate and automatic `chDB` context synchronization.

### Workflow Diagram

```mermaid
flowchart TD
    %% Styling Classes
    classDef inputNode fill:#E1F5FE,stroke:#0288D1,stroke-width:2px,color:#01579B,font-weight:bold;
    classDef agentNode fill:#FFF8E1,stroke:#FFA000,stroke-width:2px,color:#FF6F00,font-weight:bold;
    classDef toolNode fill:#F3E5F5,stroke:#8E24AA,stroke-width:2px,color:#4A148C;
    classDef gateNode fill:#FFF3E0,stroke:#FB8C00,stroke-width:2px,color:#E65100,font-weight:bold;
    classDef abortNode fill:#FFEBEE,stroke:#E53935,stroke-width:2px,color:#B71C1C;
    classDef successNode fill:#E8F5E9,stroke:#43A047,stroke-width:2px,color:#1B5E20,font-weight:bold;
    classDef dbNode fill:#EDE7F6,stroke:#5E35B1,stroke-width:2px,color:#311B92;

    %% Pipeline Nodes
    Input["Input: Feature Spec (spec.md) + Event Stream (events.ndjson)"]:::inputNode

    subgraph S1 ["1. Schema & Materialized View Generation"]
        IE["Agent: Instrumentation Engineer"]:::agentNode
        T1["Tool_Infer_Schema<br/>• (timestamp, user_id) ORDER BY<br/>• toYYYYMM Partitioning<br/>• 12-Month TTL<br/>• Categorical LowCardinality"]:::toolNode
        T2["Tool_Generate_MV<br/>• Pre-aggregated Daily Segment Rollup<br/>• SummingMergeTree Engine"]:::toolNode
        IE --> T1
        IE --> T2
    end

    subgraph S2 ["2. Human-in-the-Loop Approval Gate"]
        Gate{"Operator Prompt:<br/>Type APPROVE to execute"}:::gateNode
        Abort["Abort Execution<br/>(Zero Mutation on ClickHouse Cloud)"]:::abortNode
    end

    subgraph S3 ["3. Cloud Execution & Context Audit"]
        T3["Tool_Execute_DDL<br/>Applies DDL & MV to ClickHouse Cloud"]:::toolNode
        Reg["chDB.schema_registry<br/>(Versioned Schema History)"]:::dbNode
        CL["Agent: Context Librarian"]:::agentNode
        T4["Tool_Context_Diff<br/>Audit Denominators & Metric Gaps"]:::toolNode
        T5["Tool_Context_Upsert<br/>Sync chDB.business_context & Changelog"]:::toolNode
        Done["Pipeline Complete<br/>Schema & Context Fully Synchronized"]:::successNode

        T3 --> Reg
        T3 --> CL
        CL --> T4
        CL --> T5
        T5 --> Done
    end

    %% Connections
    Input --> S1
    S1 --> Gate
    Gate -->|Rejected / Other| Abort
    Gate -->|Approved| S3
```

### Steps Breakdown

1. **Schema Inference (`Instrumentation Engineer`)**:
   - **`Tool_Infer_Schema`**: Analyzes the NDJSON events stream and feature Markdown spec. Generates production ClickHouse DDL adhering to strict engineering constraints:
     - `ORDER BY (timestamp, user_id)` (never leads with UUID).
     - Monthly partitioning via `toYYYYMM(timestamp)`.
     - 12-month data retention TTL via `TTL timestamp + INTERVAL 12 MONTH`.
     - Flattens nested JSON objects (e.g. `payment.amount` $\rightarrow$ `payment_amount`).
     - Uses `LowCardinality(String)` for low-cardinality categorical attributes (e.g. `device_type`, `currency`).
   - **`Tool_Generate_MV`**: Inspects inferred columns for slice/segment dimensions (`device_type`, `geoip_country_code`, `destination`) and generates a companion daily pre-aggregation `SummingMergeTree` Materialized View.

2. **Human-in-the-Loop (HITL) Gate**:
   - Presents the proposed DDL and Materialized View to the operator.
   - Requires explicit literal input `"APPROVE"` to proceed. Any other input aborts immediately without touching ClickHouse Cloud.

3. **Execution & Context Audit (`Context Librarian`)**:
   - **`Tool_Execute_DDL`**: Executes DDL on ClickHouse Cloud and records versioned schema snapshot in `chDB.schema_registry`.
   - **`Tool_Context_Diff`**: Compares new table columns against `chDB.business_context`. Detects metric denominator contradictions and flags undocumented columns.
   - **`Tool_Context_Upsert`**: Upserts new metrics and column definitions into `chDB.business_context` with incremental versioning and appends audit trails to `chDB.context_changelog`.

---

## CUJ 2: Analyst Query & Anomaly Detection Interface

### Purpose
Provides product managers with an intuitive, hallucination-free conversational interface (via LibreChat UI or HTTP API). All analytical computations are executed natively in ClickHouse Cloud, and domain anomalies (K1–K7) are checked against a versioned business context layer.

### Workflow Diagram

```mermaid
flowchart TD
    %% Styling Classes
    classDef inputNode fill:#E1F5FE,stroke:#0288D1,stroke-width:2px,color:#01579B,font-weight:bold;
    classDef agentNode fill:#FFF8E1,stroke:#FFA000,stroke-width:2px,color:#FF6F00,font-weight:bold;
    classDef toolNode fill:#F3E5F5,stroke:#8E24AA,stroke-width:2px,color:#4A148C;
    classDef routerNode fill:#E0F7FA,stroke:#00ACC1,stroke-width:2px,color:#006064,font-weight:bold;
    classDef successNode fill:#E8F5E9,stroke:#43A047,stroke-width:2px,color:#1B5E20,font-weight:bold;
    classDef dbNode fill:#EDE7F6,stroke:#5E35B1,stroke-width:2px,color:#311B92;

    %% Pipeline Nodes
    Query["Product Manager Question<br/>(via LibreChat UI / HTTP POST /v1/chat/completions)"]:::inputNode

    subgraph Step1 ["1. JIT Context Retrieval"]
        JIT["JIT SQL Query to chDB.business_context<br/>Fetch active domain rules & Known Issues (K1-K7)"]:::toolNode
    end

    subgraph Step2 ["2. ClickHouse Cloud Multi-Cut Aggregation"]
        PA["Agent: Product Analyst<br/>(memory=False, No DDL Tools)"]:::agentNode
        Compute["Tool_Analytics_Compute<br/>Push down GROUP BY queries across:<br/>• device_type<br/>• geoip_country_code<br/>• destination"]:::toolNode
        PA --> Compute
    end

    subgraph Step3 ["3. Anomaly Routing & Confidence Scoring"]
        Router{"Matches Documented<br/>Known Issue (K1-K7)?"}:::routerNode
        Score["Tool_Score_Confidence<br/>Score = f(Sample Size, Effect Size, Match, Cuts) in [0, 1]"]:::toolNode
        Insight["Structured PM Markdown Insight<br/>+ OpenAI Chat Completion Response"]:::successNode
        Save["chDB.insights<br/>(Persist PM Report & Confidence Score)"]:::dbNode

        Router -->|Yes / No| Score
        Score --> Insight
        Score --> Save
    end

    %% Connections
    Query --> Step1
    Step1 --> Step2
    Step2 --> Step3
```

### Steps Breakdown

1. **Just-In-Time (JIT) Context Retrieval**:
   - Queries `chDB.business_context` using SQL (`SELECT key, definition FROM business_context WHERE ...`).
   - Retrieves active metric formulas and documented anomalies (`K1`–`K7`).
   - Eliminates hidden LLM memory drift (`memory=False`).

2. **Mandatory Multi-Cut ClickHouse Aggregation**:
   - The **Product Analyst** agent has read-only access (`SELECT` only). Non-select operations are strictly blocked.
   - Pushes down dimension aggregation queries directly to ClickHouse Cloud across mandatory cut dimensions:
     - `device_type`
     - `geoip_country_code`
     - `destination`

3. **Anomaly Routing & Confidence Scoring**:
   - **Routing**: Evaluates question keywords and dimension aggregations against retrieved context definitions (e.g. matching `K1: iOS WebKit OTP autofill regression`).
   - **`Tool_Score_Confidence`**: Calculates a deterministic confidence score:
     $$ \text{Score} = f(\text{Sample Size } N, \text{Effect Size } \Delta, \text{Known Issue Match}, \text{Cut Consistency}) \in [0, 1] $$
   - **Synthesis**: Formats a structured PM report, persists the insight to `chDB.insights`, logs the Langfuse trace span, and returns an OpenAI-compatible JSON payload to LibreChat.
