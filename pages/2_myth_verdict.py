import streamlit as st
import duckdb

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Myth Verdict Dashboard", layout="wide")
st.title("Myth Verdict Dashboard")

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE events AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
""")

# ---------------------------------------------------------
# SIDEBAR – PLAYER SELECTOR
# ---------------------------------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name
    FROM lineups
    ORDER BY player_name
""").df()

player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(f"Myth Verdict Summary for {player_name}")

# ---------------------------------------------------------
# HYPOTHESIS 1 – ADAPTATION TAX
# ---------------------------------------------------------
st.subheader("Hypothesis 1: Adaptation Tax")
st.write("**Verdict Gauge (placeholder)**")
st.empty()

st.write("**Confidence Level (placeholder)**")
st.empty()

st.write("**Impact Heatmap (placeholder)**")
st.empty()

st.markdown("---")

# ---------------------------------------------------------
# HYPOTHESIS 2 – TRANSFER TIMING
# ---------------------------------------------------------
st.subheader("Hypothesis 2: Transfer Timing")
st.write("**Verdict Gauge (placeholder)**")
st.empty()

st.write("**Confidence Level (placeholder)**")
st.empty()

st.write("**Impact Heatmap (placeholder)**")
st.empty()

st.markdown("---")

# ---------------------------------------------------------
# HYPOTHESIS 3 – Age Optimization
# ---------------------------------------------------------
st.subheader("Hypothesis 3: Age Optimization")
st.write("**Verdict Gauge (placeholder)**")
st.empty()

st.write("**Confidence Level (placeholder)**")
st.empty()

st.write("**Impact Heatmap (placeholder)**")
st.empty()

st.markdown("---")

# ---------------------------------------------------------
# HYPOTHESIS 4 – Squad Balance
# ---------------------------------------------------------
st.subheader("Hypothesis 4: Squad Balance")
st.write("**Verdict Gauge (placeholder)**")
st.empty()

st.write("**Confidence Level (placeholder)**")
st.empty()

st.write("**Impact Heatmap (placeholder)**")
st.empty()

st.markdown("---")

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.caption("Myth Verdict Dashboard – structure ready for gauges, confidence scores, and impact heatmaps.")
