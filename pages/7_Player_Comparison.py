import streamlit as st
import duckdb

st.set_page_config(page_title="Player Comparison", layout="wide")
st.title("Player Comparison Dashboard")

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE events AS SELECT * FROM read_parquet('events.parquet');
""")

# -------------------------------
# Sidebar – Player selectors
# -------------------------------
st.sidebar.title("Player Comparison")

players = con.execute("""
    SELECT DISTINCT player_id, player_name
    FROM lineups
    ORDER BY player_name
""").df()

player1 = st.sidebar.selectbox("Select Player 1", players["player_name"])
player2 = st.sidebar.selectbox("Select Player 2", players["player_name"])

id1 = int(players.loc[players["player_name"] == player1, "player_id"].iloc[0])
id2 = int(players.loc[players["player_name"] == player2, "player_id"].iloc[0])

st.markdown("---")
st.header(f"Comparing {player1} vs {player2}")

# ---------------------------------------------------------
# ATTRIBUTE COMPARISON (placeholder)
# ---------------------------------------------------------
st.subheader("Attribute Comparison")
st.write("*(Attribute comparison chart will be added here)*")
st.empty()

# ---------------------------------------------------------
# PERFORMANCE COMPARISON (placeholder)
# ---------------------------------------------------------
st.subheader("Performance Comparison")
st.write("*(Performance comparison graph will be added here)*")
st.empty()

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.caption("Player Comparison Dashboard – placeholders ready for attribute and performance comparison.")
