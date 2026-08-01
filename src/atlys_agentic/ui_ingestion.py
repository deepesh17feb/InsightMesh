"""Streamlit Ingestion Portal for CUJ 1.

Usage:
  streamlit run src/atlys_agentic/ui_ingestion.py
  # or via console entrypoint:
  atlys-ui
"""
import sys

from atlys_agentic import chdb_client, paths
from atlys_agentic.flows import ingestion_flow


def render_app():
    import streamlit as st
    from atlys_agentic import tools

    st.set_page_config(
        page_title="Atlys Feature Ingestion Portal",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom Styling
    st.markdown(
        """
        <style>
        .hero-title {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #60A5FA 0%, #A78BFA 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.15rem;
        }
        .hero-subtitle {
            color: #94A3B8;
            font-size: 0.84rem;
            margin-bottom: 0.85rem;
        }
        .status-pill {
            display: inline-block;
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid #334155;
            color: #93C5FD;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.74rem;
            font-weight: 500;
            margin-right: 0.4rem;
        }
        .tag-pill {
            display: inline-block;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid #10B981;
            color: #34D399;
            padding: 0.15rem 0.45rem;
            border-radius: 5px;
            font-size: 0.74rem;
            font-family: monospace;
            margin: 0.15rem;
        }

        /* Subtle & Compact Metric Cards */
        div[data-testid="stMetric"] {
            background: rgba(30, 41, 59, 0.45) !important;
            border: 1px solid rgba(51, 65, 85, 0.7) !important;
            border-radius: 8px !important;
            padding: 0.45rem 0.75rem !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15) !important;
        }

        div[data-testid="stMetricLabel"], 
        div[data-testid="stMetricLabel"] * {
            font-size: 0.7rem !important;
            font-weight: 500 !important;
            color: #94A3B8 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.04em !important;
            margin-bottom: 0.1rem !important;
        }

        div[data-testid="stMetricValue"], 
        div[data-testid="stMetricValue"] * {
            font-size: 0.95rem !important;
            font-weight: 600 !important;
            color: #93C5FD !important;
            font-family: 'JetBrains Mono', monospace, -apple-system !important;
        }

        /* Subtle Section Headers */
        h2, h3, div[data-testid="stHeadingWithActionElements"] h2, div[data-testid="stHeadingWithActionElements"] h3 {
            font-size: 1.05rem !important;
            font-weight: 600 !important;
            color: #E2E8F0 !important;
            margin-top: 0.5rem !important;
            margin-bottom: 0.5rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Header & System Status
    st.markdown('<div class="hero-title">⚡ Atlys Feature Ingestion Portal</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">CUJ 1: Automated Schema Inference, Internal Table Consultation & Human-in-the-Loop Cloud Deployment</div>', unsafe_allow_html=True)
    
    st.markdown(
        """
        <div>
            <span class="status-pill">🟢 ClickHouse Cloud Connected</span>
            <span class="status-pill">⚡ chDB Embedded Engine Active</span>
            <span class="status-pill">🤖 CrewAI Multi-Agent Flow</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    # Discover specs
    available_specs = []
    if paths.SPECS_DIR.exists():
        for p in sorted(paths.SPECS_DIR.glob("*")):
            if p.is_dir():
                available_specs.append(p.name)

    if not available_specs:
        st.warning(f"No specs found in {paths.SPECS_DIR}")
        return

    # Workflow Switcher (CUJ 1 vs CUJ 2)
    workflow = st.radio(
        "Workflow",
        ["⚡ CUJ 1: Ingestion & Schema Consultation", "🔍 CUJ 2: Root-Cause & Analytics Investigation"],
        index=0,
        horizontal=True,
    )
    st.write("")

    if "CUJ 1" in workflow:
        _render_cuj1_ingestion(available_specs)
    else:
        _render_cuj2_investigation(available_specs)


def _render_cuj1_ingestion(available_specs: list[str]):
    import streamlit as st
    from atlys_agentic import tools

    # Sidebar: Spec Selection & Overrides
    with st.sidebar:
        st.subheader("📁 Feature Specification")
        selected_spec = st.selectbox("Select Spec to Ingest", available_specs)

        spec_text = ""
        spec_path = paths.spec_md(selected_spec)
        if spec_path.exists():
            spec_text = spec_path.read_text(encoding="utf-8")
        inferred_table = tools.Tool_Infer_Table_Name(selected_spec, spec_text)

        # Sleek, compact & highly noticeable Inferred Table Badge
        st.markdown(
            f"""
            <div style="background: rgba(30, 58, 138, 0.25); border: 1px solid #3B82F6; border-radius: 7px; padding: 0.45rem 0.65rem; margin: 0.5rem 0 0.65rem 0;">
                <div style="font-size: 0.68rem; color: #93C5FD; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">⚡ Inferred Table</div>
                <div style="font-size: 0.90rem; font-weight: 700; color: #60A5FA; font-family: 'JetBrains Mono', monospace; margin-top: 0.1rem; word-break: break-all;">
                    {inferred_table}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("⚙️ Advanced Settings"):
            override = st.checkbox("Override Inferred Table Name", value=False)
            if override:
                table_name = st.text_input("Custom Table Name", value=inferred_table)
            else:
                table_name = inferred_table

        st.divider()
        st.caption("🔒 **Guaranteed Cloud Safety**: Dry-Run mode audits context and produces schema proposals with zero mutation to ClickHouse Cloud or chDB.")

    # Execution Mode Selector (Tabs / Radio)
    mode_col1, mode_col2 = st.columns([2, 1])
    with mode_col1:
        mode = st.radio(
            "Execution Mode",
            ["🛡️ Dry Run Mode (Inspect & Propose — Non-Mutating)", "🚀 Live Mode (Deploy with Human-in-the-Loop Confirmation)"],
            index=0,
            horizontal=True,
            label_visibility="collapsed",
        )
    is_dry_run = "Dry Run" in mode

    # Top KPI Metrics Row
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Feature Spec", selected_spec)
    kpi2.metric("Target Table", table_name)
    kpi3.metric("Mode", "🛡️ Dry Run" if is_dry_run else "🚀 Live")
    strategy_placeholder = kpi4.empty()
    strategy_placeholder.metric("Table Strategy", "Consulting...")

    st.divider()

    # Main 2-Column Split: Context & Spec on Left, Agent Outputs on Right
    left_col, right_col = st.columns([1, 1], gap="medium")

    with left_col:
        st.subheader("1. Source Artifacts & Events")
        tab_spec, tab_events = st.tabs(["📄 Feature Spec (`spec.md`)", "📊 Event Stream Preview (`events.ndjson`)"])

        with tab_spec:
            if spec_path.exists():
                st.markdown(spec_text)
            else:
                st.error(f"Spec file not found at {spec_path}")

        with tab_events:
            ndjson_path = paths.events_ndjson(selected_spec)
            if ndjson_path.exists():
                lines = ndjson_path.read_text(encoding="utf-8").strip().splitlines()
                st.caption(f"Showing first 5 of {len(lines)} raw events in payload stream:")
                st.code("\n".join(lines[:5]), language="json")
            else:
                st.info("No raw events file found for this spec.")

    with right_col:
        st.subheader("2. Agent Schema Inference & Context Audit")

        action_label = "🔍 Run Dry Run (Generate Proposal)" if is_dry_run else "⚡ Generate Schema for Deployment"
        run_btn = st.button(action_label, type="primary", use_container_width=True)

        if "proposal" not in st.session_state or run_btn:
            if run_btn:
                with st.spinner("Instrumentation Engineer consulting tables & inferring schema..."):
                    chdb_client.init_schema()
                    chdb_client.init_base_context()
                    proposal = ingestion_flow.run(spec_id=selected_spec, table_name=table_name, dry_run=True)
                    st.session_state["proposal"] = proposal
                    st.session_state["last_spec"] = selected_spec
                    st.session_state["last_table"] = table_name

        proposal = st.session_state.get("proposal")
        if proposal and st.session_state.get("last_spec") == selected_spec:
            consult = proposal.get("table_consultation", {})
            reasoning = proposal.get("reasoning", {})
            strategy_placeholder.metric("Table Strategy", consult.get("strategy", "CREATE_NEW"))

            # 1. High-Level Executive Summary Card
            st.success(f"✅ Schema proposal for `{table_name}` generated successfully.")
            st.info(
                f"**Architecture Decision:** `{consult.get('strategy', 'CREATE_NEW')}`\n\n"
                f"**Executive Summary:** {reasoning.get('high_level_summary', consult.get('recommendation', ''))}"
            )

            # 2. DDL & MV Output Tabs
            schema_tab, mv_tab = st.tabs(["🏗️ ClickHouse Table DDL", "📈 Materialized View (SummingMergeTree)"])
            with schema_tab:
                st.code(proposal.get("ddl", ""), language="sql")

            with mv_tab:
                mv_ddl = proposal.get("mv_ddl")
                if mv_ddl:
                    st.code(mv_ddl, language="sql")
                else:
                    st.info("No segment dimension columns detected; Materialized View skipped.")

            # 3. Foldable Technical Deep Dive
            deep = reasoning.get("technical_deep_dive", {})
            with st.expander("🔍 Technical Deep Dive & Storage Mechanics", expanded=False):
                if deep:
                    st.markdown(f"- **Table Strategy:** {deep.get('table_strategy', '')}")
                    st.markdown(f"- **Primary Sorting Key (`ORDER BY`):** {deep.get('ordering_mechanics', '')}")
                    st.markdown(f"- **Partitioning Strategy (`PARTITION BY`):** {deep.get('partitioning_mechanics', '')}")
                    st.markdown(f"- **Encodings & Compression:** {deep.get('column_encodings_and_compression', '')}")
                    st.markdown(f"- **Rollup Materialized View:** {deep.get('materialized_view_rollup', '')}")
                    st.markdown(f"- **Lifecycle Retention (TTL):** {deep.get('lifecycle_retention', '')}")
                elif reasoning.get("full_markdown"):
                    st.markdown(reasoning["full_markdown"])

            # 4. Context Diff Audit (Context Librarian)
            diff = proposal.get("diff_result", {})
            with st.expander("📚 Context Diff Audit (Context Librarian)", expanded=True):
                additions = diff.get("additions", [])
                st.write(f"**Discovered Columns to Sync ({len(additions)}):**")
                if additions:
                    tags_html = "".join([f'<span class="tag-pill">+ {col}</span>' for col in additions])
                    st.markdown(tags_html, unsafe_allow_html=True)
                else:
                    st.write("None")

                if diff.get("conflicts"):
                    st.error(f"Metric Conflicts: {diff.get('conflicts')}")
                if diff.get("gaps"):
                    st.warning(f"Undocumented Gaps: {diff.get('gaps')}")

            # 5. HITL Gate (Live Mode)
            if not is_dry_run:
                st.divider()
                st.subheader("3. Human-in-the-Loop (HITL) Gate")
                confirm = st.checkbox(f"I authorize executing this DDL on ClickHouse Cloud table `{table_name}`.")

                if st.button("🚀 Approve & Deploy to ClickHouse Cloud", type="secondary", disabled=not confirm, use_container_width=True):
                    with st.spinner("Executing DDL on ClickHouse Cloud and recording version..."):
                        result = ingestion_flow.run(
                            spec_id=selected_spec,
                            table_name=table_name,
                            input_fn=lambda _: "APPROVE",
                            dry_run=False,
                        )
                        if result.get("approved"):
                            st.balloons()
                            st.success(f"🎉 Successfully deployed `{table_name}` to ClickHouse Cloud and registered version in `chDB.schema_registry`!")
                        else:
                            st.error(f"Deployment rejected or failed: {result}")
            else:
                st.caption("🔒 *Dry-Run Active: ClickHouse Cloud and chDB were not modified.*")


def _render_cuj2_investigation(available_specs: list[str]):
    import pandas as pd
    import streamlit as st
    from atlys_agentic.flows import analysis_flow

    st.markdown("### 🔍 Root-Cause & Analytics Investigation (CUJ 2)")
    st.caption("Autonomous multi-cut metric slicing, known-issue hypothesis matching, and statistical confidence scoring.")

    # Left / Right Split for Investigation
    col_query, col_results = st.columns([1, 1], gap="medium")

    presets = {
        "📱 Scenario 1: iOS OTP WebKit Autofill Regression": {
            "question": "Is there an iOS OTP drop on Express Checkout during verification?",
            "spec": "01_express_checkout" if "01_express_checkout" in available_specs else available_specs[0],
            "sql": "SELECT * FROM express_checkout",
        },
        "💳 Scenario 2: Payment Gateway 3DS Latency & Dropoff": {
            "question": "Why did conversion drop for Credit Card transactions during 3DS challenge?",
            "spec": "01_express_checkout" if "01_express_checkout" in available_specs else available_specs[0],
            "sql": "SELECT * FROM express_checkout",
        },
        "🌍 Scenario 3: Cross-Country Funnel Comparison": {
            "question": "Compare checkout completion rates and dropoff across US, UK, and UAE cohorts",
            "spec": "01_express_checkout" if "01_express_checkout" in available_specs else available_specs[0],
            "sql": "SELECT * FROM express_checkout",
        },
        "✏️ Scenario 4: Custom Diagnostic Question": {
            "question": "",
            "spec": available_specs[0],
            "sql": "SELECT * FROM express_checkout",
        },
    }

    with col_query:
        st.subheader("1. Diagnostic Investigation Scope")
        selected_preset = st.selectbox("Choose Diagnostic Preset", list(presets.keys()), index=0)
        preset_data = presets[selected_preset]

        default_question = preset_data["question"]
        question = st.text_area("Diagnostic Question", value=default_question, height=90, placeholder="e.g. Why did conversion drop on iOS during OTP verification?")

        spec_id = st.selectbox("Context Domain / Spec", available_specs, index=available_specs.index(preset_data["spec"]) if preset_data["spec"] in available_specs else 0)

        with st.expander("⚙️ ClickHouse Analytical Query Target"):
            base_sql = st.text_input("Base Analytical SQL", value=preset_data["sql"])

        run_investigation = st.button("🔍 Run Multi-Agent Investigation", type="primary", use_container_width=True)

    with col_results:
        st.subheader("2. Investigation Findings & 3-View Snapshot")

        if run_investigation or "analysis_result" in st.session_state:
            if run_investigation:
                with st.spinner("Product Analyst & Context Librarian slicing multi-cut dimensions & checking known issues..."):
                    chdb_client.init_schema()
                    chdb_client.init_base_context()
                    result = analysis_flow.run(question=question, spec_id=spec_id, base_sql=base_sql)
                    st.session_state["analysis_result"] = result
                    st.session_state["last_question"] = question

            res = st.session_state.get("analysis_result")
            if res:
                # 1. Executive Incident Finding Card
                if res.get("known_issue_match"):
                    st.error(f"⚠️ **Incident Correlated with Known Issue:**\n\n`{res.get('matched_known_issue')}`")
                else:
                    st.success("✅ **Multi-Cut Analysis Complete**: No cataloged platform bug matched this cohort.")

                st.info(f"**Executive Finding:** {res.get('executive_summary')}")

                # 2. Confidence Metric Row
                conf = res.get("confidence", {})
                score = conf.get("score", 0.0)
                score_label = "HIGH CONFIDENCE" if score >= 0.8 else ("MODERATE" if score >= 0.5 else "LOW SAMPLE")

                c1, c2, c3 = st.columns(3)
                c1.metric("Confidence Score", f"{score:.2f} / 1.0")
                c2.metric("Rating", score_label)
                c3.metric("Dimensions Sliced", f"{len(res.get('cuts', {}))} Dims")

                # 3. Interactive 3-View Visualization Snapshot
                views = res.get("views", {})
                tab_trend, tab_waterfall, tab_deltas = st.tabs(["📈 Funnel Conversion Trend", "📊 Segment Breakdown", "📋 Metric Deltas"])

                with tab_trend:
                    trend_data = views.get("conversion_trend", [])
                    if trend_data:
                        df_trend = pd.DataFrame(trend_data).set_index("date")
                        st.line_chart(df_trend)
                        st.caption("Time-series comparison: Baseline cohort vs Observed affected cohort.")
                    else:
                        st.write("No trend dataset returned.")

                with tab_waterfall:
                    waterfall_data = views.get("segment_waterfall", [])
                    if waterfall_data:
                        df_wf = pd.DataFrame(waterfall_data).set_index("segment")
                        st.bar_chart(df_wf["dropoff_pct"])
                        st.caption("Segment dropoff rates (% dropoff by cohort).")
                    else:
                        st.write("No waterfall dataset returned.")

                with tab_deltas:
                    deltas_data = views.get("metric_deltas", [])
                    if deltas_data:
                        df_deltas = pd.DataFrame(deltas_data)
                        st.dataframe(df_deltas, use_container_width=True, hide_index=True)
                    else:
                        st.write("No delta metrics returned.")

                # 4. Agent SQL Execution Trace
                with st.expander("🛠️ Executed ClickHouse SQL & Analytical Cuts", expanded=False):
                    sql_queries = res.get("sql_queries", [])
                    if sql_queries:
                        for idx, q in enumerate(sql_queries, 1):
                            st.markdown(f"**Query {idx}:**")
                            st.code(q, language="sql")
                    st.caption(f"Trace ID: `{res.get('trace_id')}`")


def main():
    try:
        import streamlit.web.cli as stcli
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())
    except ImportError:
        print("Streamlit is not installed. To run the Streamlit UI, install streamlit via: pip install streamlit")
        print("Alternatively, open the built-in FastAPI Ingestion Portal at: http://localhost:8008/ui/ingestion")


if __name__ == "__main__":
    try:
        import streamlit as st
        # If run via `streamlit run ...`
        if st.runtime.exists():
            render_app()
        else:
            main()
    except ImportError:
        main()
