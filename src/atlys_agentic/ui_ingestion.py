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

    st.set_page_config(
        page_title="Atlys Feature Ingestion Portal",
        page_icon="⚡",
        layout="wide",
    )

    st.title("⚡ Atlys Feature Ingestion Portal")
    st.caption("CUJ 1: Automated ClickHouse Schema Inference, Materialized View Generation & Context Audit")

    # Discover specs
    available_specs = []
    if paths.SPECS_DIR.exists():
        for p in sorted(paths.SPECS_DIR.glob("*")):
            if p.is_dir():
                available_specs.append(p.name)

    if not available_specs:
        st.warning(f"No specs found in {paths.SPECS_DIR}")
        return

    with st.sidebar:
        st.header("Ingestion Configuration")
        selected_spec = st.selectbox("Select Feature Specification", available_specs)
        default_table = selected_spec.split("_", 1)[-1] if "_" in selected_spec else selected_spec
        table_name = st.text_input("Target ClickHouse Table Name", value=default_table)
        st.divider()
        st.info("💡 **Dry Run Mode**: Inactive mutation. Inspects events, generates DDL, and audits context without modifying ClickHouse Cloud or chDB.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Feature Specification & Events")
        spec_path = paths.spec_md(selected_spec)
        if spec_path.exists():
            with st.expander("📄 Feature Specification (`spec.md`)", expanded=True):
                st.markdown(spec_path.read_text(encoding="utf-8"))
        else:
            st.error(f"Spec file not found at {spec_path}")

        ndjson_path = paths.events_ndjson(selected_spec)
        if ndjson_path.exists():
            with st.expander("📊 Raw Event Stream Preview (`events.ndjson`)", expanded=False):
                lines = ndjson_path.read_text(encoding="utf-8").strip().splitlines()[:5]
                st.code("\n".join(lines), language="json")

    with col2:
        st.subheader("2. Schema Proposal & Cloud Deployment")

        run_dry_run = st.button("🔍 Generate Proposal (Dry Run)", type="primary", use_container_width=True)

        if "proposal" not in st.session_state or run_dry_run:
            if run_dry_run:
                with st.spinner("Analyzing spec and inferring optimal schema..."):
                    chdb_client.init_schema()
                    chdb_client.init_base_context()
                    proposal = ingestion_flow.run(spec_id=selected_spec, table_name=table_name, dry_run=True)
                    st.session_state["proposal"] = proposal
                    st.session_state["last_spec"] = selected_spec
                    st.session_state["last_table"] = table_name

        proposal = st.session_state.get("proposal")
        if proposal and st.session_state.get("last_spec") == selected_spec:
            st.success("✅ Schema proposal generated successfully (Dry Run).")

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

            st.divider()
            st.subheader("3. Human-in-the-Loop (HITL) Gate")
            confirm = st.checkbox("I have reviewed the proposed DDL and authorize deployment to ClickHouse Cloud.")

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
                        st.success(f"🎉 Successfully deployed `{table_name}` to ClickHouse Cloud and updated `chDB.schema_registry`!")
                    else:
                        st.error(f"Deployment rejected or failed: {result}")


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
