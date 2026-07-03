import streamlit as st
import duckdb

st.set_page_config(page_title="Adaptation Analysis", layout="wide")
st.title("Adaptation Analysis Dashboard")

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE events AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
""")

# -------------------------------
# Sidebar – Player selector
# -------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name
    FROM lineups
    ORDER BY player_name
""").df()

player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(f"Adaptation Analysis for {player_name}")

# ---------------------------------------------------------
# ADAPTATION CURVE (placeholder)
# ---------------------------------------------------------
st.subheader("Adaptation Curve Over Matches")
st.write("*(Graph will be added here)*")
st.empty()

# ---------------------------------------------------------
# ADAPTATION SCORE (placeholder)
# ---------------------------------------------------------
st.subheader("Adaptation Score")
st.write("*(Score will be added here)*")
st.empty()

# ---------------------------------------------------------
# ROLLING PERFORMANCE (placeholder)
# ---------------------------------------------------------
st.subheader("Rolling Performance")
st.write("*(Rolling performance graph will be added here)*")
st.empty()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.caption("Adaptation Analysis Dashboard – placeholders ready for adaptation curve, score, and rolling performance.")
