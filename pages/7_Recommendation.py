import streamlit as st
import duckdb

st.set_page_config(page_title="Recommendation Engine", layout="wide")
st.title("Recommendation Dashboard")

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE events AS SELECT * FROM read_parquet('events.parquet');
""")

# -------------------------------
# Sidebar – Team selector
# -------------------------------
st.sidebar.title("Recommendation Settings")

teams = con.execute("""
    SELECT DISTINCT team_id
    FROM lineups
    ORDER BY team_id
""").df()

team_id = st.sidebar.selectbox("Select Team", teams["team_id"])

st.markdown("---")
st.header(f"Recommendation Engine for Team {team_id}")

# ---------------------------------------------------------
# IDEAL SIGNINGS (placeholder)
# ---------------------------------------------------------
st.subheader("Ideal Signings")
st.write("*(List of recommended signings will be added here)*")
st.empty()

# ---------------------------------------------------------
# AI-BASED RECOMMENDATION SCORE (placeholder)
# ---------------------------------------------------------
st.subheader("AI-Based Recommendation Score")
st.write("*(Gauge chart will be added here)*")
st.empty()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.caption("Recommendation Dashboard – placeholders ready for ideal signings and AI-based recommendation score.")
