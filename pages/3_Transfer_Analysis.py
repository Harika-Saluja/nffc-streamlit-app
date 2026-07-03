import streamlit as st
import duckdb

st.set_page_config(page_title="Transfer Analysis", layout="wide")
st.title("Transfer Analysis Dashboard")

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
st.header(f"Transfer Analysis for {player_name}")

# ---------------------------------------------------------
# TRANSFER TREND LINE (placeholder)
# ---------------------------------------------------------
st.subheader("Transfer Trend Line")
st.write("*(Graph will be added here)*")
st.empty()

# ---------------------------------------------------------
# FITNESS LOAD BEFORE/AFTER TRANSFER (placeholder)
# ---------------------------------------------------------
st.subheader("Fitness Load Before/After Transfer")
st.write("*(Gauge chart will be added here)*")
st.empty()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.caption("Transfer Analysis Dashboard – placeholders ready for trend line and fitness load gauge.")
