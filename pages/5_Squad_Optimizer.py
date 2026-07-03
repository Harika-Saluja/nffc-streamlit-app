import streamlit as st
import duckdb

st.set_page_config(page_title="Squad Optimizer", layout="wide")
st.title("Squad Optimizer Dashboard")

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
st.sidebar.title("Team Selector")

teams = con.execute("""
    SELECT DISTINCT team_id
    FROM lineups
    ORDER BY team_id
""").df()

team_id = st.sidebar.selectbox("Select Team", teams["team_id"])

st.markdown("---")
st.header(f"Squad Optimizer for Team {team_id}")

# ---------------------------------------------------------
# SQUAD COMPOSITION (placeholder)
# ---------------------------------------------------------
st.subheader("Squad Composition")
st.write("*(Squad composition chart will be added here)*")
st.empty()

# ---------------------------------------------------------
# FORMATION HEATMAP (placeholder)
# ---------------------------------------------------------
st.subheader("Formation Heatmap")
st.write("*(Formation heatmap will be added here)*")
st.empty()

# ---------------------------------------------------------
# AVAILABILITY MATRIX (placeholder)
# ---------------------------------------------------------
st.subheader("Availability Matrix")
st.write("*(Availability matrix will be added here)*")
st.empty()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.caption("Squad Optimizer Dashboard – placeholders ready for composition, heatmap, and availability matrix.")
