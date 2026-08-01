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
    )

    st.title("⚡ Atlys Agentic Analytics Platform")
    st.caption("CUJ 1: Feature Ingestion & CUJ 2: Real-Time Visualization Snapshot Dashboard")

    tab_ingest, tab_viz = st.tabs(["⚡ CUJ 1: Feature Ingestion Portal", "📊 3-View Real-Time Snapshot Dashboard"])

    with tab_ingest:
        # Top-level Mode Selector
        mode = st.radio(
            "Ingestion Execution Mode:",
            ["🛡️ Dry Run Mode (Inspect & Propose — Zero Cloud Mutation)", "🚀 Live Mode (Deploy to ClickHouse Cloud with HITL Gate)"],
            index=0,
            horizontal=True,
        )
        is_dry_run = "Dry Run" in mode

        if is_dry_run:
            st.info("🛡️ **Dry Run Mode Active**: The agent infers schemas, creates Materialized Views, and audits `business_context` without mutating ClickHouse Cloud or chDB.")
        else:
            st.warning("⚠️ **Live Deployment Mode**: Proposed DDL and Materialized Views will be executed on ClickHouse Cloud upon your approval.")

        st.divider()

        # Sidebar: Spec Selection & Auto-inferred Table Name
        with st.sidebar:
            st.header("Feature Specification")
            selected_spec = st.selectbox("Select Spec", available_specs)

            # Agent auto-infers table name from spec.md or spec ID
            spec_text = ""
            spec_path = paths.spec_md(selected_spec)
            if spec_path.exists():
                spec_text = spec_path.read_text(encoding="utf-8")
            inferred_table = tools.Tool_Infer_Table_Name(selected_spec, spec_text)

            st.metric("Inferred Table Name", inferred_table, help="Inferred automatically by the Instrumentation Engineer agent from the spec.")

            override = st.checkbox("⚙️ Override Inferred Table Name")
            if override:
                table_name = st.text_input("Custom Table Name", value=inferred_table)
            else:
                table_name = inferred_table

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("1. Feature Specification & Events")
            if spec_path.exists():
                with st.expander("📄 Feature Specification (`spec.md`)", expanded=True):
                    st.markdown(spec_text)
            else:
                st.error(f"Spec file not found at {spec_path}")

            ndjson_path = paths.events_ndjson(selected_spec)
            if ndjson_path.exists():
                with st.expander("📊 Raw Event Stream Preview (`events.ndjson`)", expanded=False):
                    lines = ndjson_path.read_text(encoding="utf-8").strip().splitlines()[:5]
                    st.code("\n".join(lines), language="json")

        with col2:
            st.subheader("2. Agent Schema Inference & Context Audit")

            action_label = "🔍 Run Dry Run (Generate Proposal)" if is_dry_run else "⚡ Generate Schema for Deployment"
            run_btn = st.button(action_label, type="primary", use_container_width=True)

            if "proposal" not in st.session_state or run_btn:
                if run_btn:
                    with st.spinner("Instrumentation Engineer analyzing spec & events..."):
                        chdb_client.init_schema()
                        chdb_client.init_base_context()
                        proposal = ingestion_flow.run(spec_id=selected_spec, table_name=table_name, dry_run=True)
                        st.session_state["proposal"] = proposal
                        st.session_state["last_spec"] = selected_spec
                        st.session_state["last_table"] = table_name

            proposal = st.session_state.get("proposal")
            if proposal and st.session_state.get("last_spec") == selected_spec:
                st.success(f"✅ Schema proposal for `{table_name}` generated successfully.")

                with st.expander("🏗️ Proposed ClickHouse Table DDL", expanded=True):
                    st.code(proposal.get("ddl", ""), language="sql")

                mv_ddl = proposal.get("mv_ddl")
                if mv_ddl:
                    with st.expander("📈 Proposed Materialized View (SummingMergeTree)", expanded=True):
                        st.code(mv_ddl, language="sql")

                diff = proposal.get("diff_result", {})
                with st.expander("📚 Context Diff Audit (Context Librarian)", expanded=True):
                    additions = diff.get("additions", [])
                    st.write(f"**Discovered Columns ({len(additions)}):**")
                    st.write(", ".join([f"`{c}`" for c in additions]) if additions else "None")
                    if diff.get("conflicts"):
                        st.error(f"Metric Conflicts: {diff.get('conflicts')}")
                    if diff.get("gaps"):
                        st.warning(f"Undocumented Gaps: {diff.get('gaps')}")

                if not is_dry_run:
                    st.divider()
                    st.subheader("3. Human-in-the-Loop (HITL) Gate")
                    confirm = st.checkbox(f"I authorize deploying `{table_name}` to ClickHouse Cloud.")

                    if st.button("🚀 Approve & Deploy to ClickHouse Cloud", type="secondary", disabled=not confirm, use_container_width=True):
                        with st.spinner("Deploying DDL and synchronizing context layer..."):
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

    with tab_viz:
        st.subheader("📊 Real-Time Three-View Snapshot")
        st.caption("Live state of Schema Registry, Product Insights, and Context Changelog from `chDB`")

        col_refresh, _ = st.columns([1, 4])
        with col_refresh:
            refresh_clicked = st.button("🔄 Refresh Snapshot", use_container_width=True)

        chdb_client.init_schema()
        chdb_client.init_base_context()
        snapshot = tools.Tool_Emit_Viz()

        schemas = snapshot.get("schema_history", [])
        insights = snapshot.get("insights", [])
        changelogs = snapshot.get("context_changelog", [])

        # KPI Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Registered Schemas", len(schemas))
        m2.metric("Product Insights", len(insights))
        m3.metric("Context Mutations", len(changelogs))
        avg_conf = 0
        if insights:
            avg_conf = round(sum(float(i.get("confidence", 0)) for i in insights) / len(insights) * 100)
        m4.metric("Avg Insight Confidence", f"{avg_conf}%")

        st.divider()

        # View 1: Schema Registry
        st.markdown("### 1. Schema Registry (Versioned DDL Snapshots)")
        if schemas:
            import pandas as pd
            df_schemas = pd.DataFrame(schemas)
            display_cols = [c for c in ["table_name", "table", "version", "spec_id", "created_at"] if c in df_schemas.columns]
            st.dataframe(df_schemas[display_cols], use_container_width=True)

            for idx, s in enumerate(schemas[:3]):
                tbl = s.get("table_name") or s.get("table") or f"table_{idx}"
                with st.expander(f"🔍 DDL Definition: {tbl} (v{s.get('version', 1)})"):
                    st.code(s.get("ddl", "(DDL recorded in schema_registry)"), language="sql")
        else:
            st.info("No tables in schema registry yet. Ingest a spec from Tab 1 to register schema snapshots.")

        st.divider()

        # View 2: Insights Feed
        st.markdown("### 2. Product Insights & Confidence Feed")
        if insights:
            for ins in insights:
                conf = float(ins.get("confidence", 0))
                with st.container(border=True):
                    ic1, ic2 = st.columns([3, 1])
                    with ic1:
                        st.markdown(f"**Question:** {ins.get('question', 'Product Question')}")
                        st.caption(f"Spec ID: `{ins.get('spec_id', 'general')}` | Created: {ins.get('created_at', 'recent')}")
                    with ic2:
                        st.progress(conf, text=f"Confidence: {round(conf*100)}%")
                    st.markdown(ins.get("answer_md", "Insight output recorded."))
        else:
            st.info("No product insights generated yet. Insights are recorded when analysts run queries through the analytical pipeline.")

        st.divider()

        # View 3: Context Changelog
        st.markdown("### 3. Business Context Changelog Audit Trail")
        if changelogs:
            import pandas as pd
            df_changes = pd.DataFrame(changelogs)
            st.dataframe(df_changes, use_container_width=True)
        else:
            st.info("No context changelog mutations logged yet.")


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
