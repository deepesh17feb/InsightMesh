import pandas as pd
import streamlit as st

from atlys_agentic import tools


def load_snapshot() -> dict:
    return tools.Tool_Emit_Viz()


def render_dashboard() -> None:
    st.set_page_config(page_title="Atlys Agentic Analytics — Deliverable #4b", layout="wide")
    st.title("Atlys Agentic Analytics — Visualization Layer")

    snapshot = load_snapshot()

    st.header("Schema changes over time")
    st.dataframe(pd.DataFrame(snapshot["schema_history"]), use_container_width=True)

    st.header("Insights with confidence scores")
    insights_df = pd.DataFrame(snapshot["insights"])
    st.dataframe(insights_df, use_container_width=True)
    if not insights_df.empty and "confidence" in insights_df:
        st.bar_chart(insights_df.set_index("question")["confidence"])

    st.header("Context diff / changelog")
    st.dataframe(pd.DataFrame(snapshot["context_changelog"]), use_container_width=True)


if __name__ == "__main__":
    render_dashboard()
