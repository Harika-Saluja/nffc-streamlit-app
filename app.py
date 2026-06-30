# app.py — Player Profile Dashboard
import streamlit as st
import duckdb
import pandas as pd

st.set_page_config(page_title="Player Profile Dashboard", layout="wide")

# ---------------------------------------------------------
# 🟩 Load data safely and cache for performance
# ---------------------------------------------------------
@st.cache_data
def load_data():
    con = duckdb.connect(database=':memory:')
    try:
        con.execute("""
            CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
            CREATE TABLE events AS SELECT * FROM read_parquet('events.parquet');
            CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
            CREATE TABLE injuries AS SELECT * FROM read_parquet('injuries.parquet');
            CREATE TABLE catapult AS SELECT * FROM read_parquet('catapult.parquet');
        """)
        st.success("✅ Parquet files loaded successfully!")
    except Exception as e:
        st.error(f"❌ Could not load Parquet files: {e}")
        st.stop()
    return con

con = load_data()

# ---------------------------------------------------------
# 🟦 Sidebar — Player selection
# ---------------------------------------------------------
player_list = con.execute("SELECT DISTINCT player_name FROM lineups ORDER BY player_name").df()["player_name"].tolist()
selected_player = st.sidebar.selectbox("Select Player", player_list)

# ---------------------------------------------------------
# 🟨 Retrieve player profile
# ---------------------------------------------------------
bio_query = f"""
    SELECT player_id, player_name, player_nickname, birth_date, player_gender,
           player_height, player_weight, jersey_number, country, formations
    FROM lineups
    WHERE player_name = '{selected_player}'
    LIMIT 1
"""
bio = con.execute(bio_query).df()

if bio.empty:
    st.warning(f"No data found for {selected_player}")
    st.stop()

player_id = int(bio["player_id"].iloc[0])

# ---------------------------------------------------------
# 🟥 Layout — Player Bio
# ---------------------------------------------------------
st.title(f"Player Profile — {selected_player}")

col1, col2 = st.columns(2)
with col1:
    st.subheader("🧍 Player Information")
    st.write(f"**Nickname:** {bio['player_nickname'].iloc[0]}")
    st.write(f"**Birth Date:** {bio['birth_date'].iloc[0]}")
    st.write(f"**Gender:** {bio['player_gender'].iloc[0]}")
    st.write(f"**Country:** {bio['country'].iloc[0]}")
    st.write(f"**Formation:** {bio['formations'].iloc[0]}")

with col2:
    st.subheader("📏 Physical Attributes")
    st.write(f"**Height:** {bio['player_height'].iloc[0]} cm")
    st.write(f"**Weight:** {bio['player_weight'].iloc[0]} kg")
    st.write(f"**Jersey Number:** {bio['jersey_number'].iloc[0]}")

# ---------------------------------------------------------
# 🟧 Match Summary
# ---------------------------------------------------------
st.subheader("⚽ Match Summary")
matches = con.execute(f"""
    SELECT match_id, competition, season, kickoff_time, venue
    FROM matches
    WHERE match_id IN (
        SELECT DISTINCT match_id FROM events WHERE player_id = {player_id}
    )
    ORDER BY kickoff_time DESC
""").df()

st.dataframe(matches)

# ---------------------------------------------------------
# 🟪 Injuries Overview
# ---------------------------------------------------------
st.subheader("🚑 Injury History")
inj = con.execute(f"""
    SELECT injury_type, start_date, end_date, recovery_days
    FROM injuries
    WHERE player_id = {player_id}
    ORDER BY start_date DESC
""").df()

st.dataframe(inj)

# ---------------------------------------------------------
# 🟫 Physical Load (Catapult data)
# ---------------------------------------------------------
st.subheader("📊 Physical Load Summary")
cat = con.execute(f"""
    SELECT session_date, total_distance, high_speed_distance, sprint_count, max_velocity
    FROM catapult
    WHERE player_id = {player_id}
    ORDER BY session_date DESC
""").df()

st.dataframe(cat)

# ---------------------------------------------------------
# 🟦 Technical Events
# ---------------------------------------------------------
st.subheader("🎯 Technical Performance")
events_df = con.execute(f"""
    SELECT event_type, outcome, minute, second, match_id
    FROM events
    WHERE player_id = {player_id}
    ORDER BY match_id, minute
""").df()

st.dataframe(events_df)

# ---------------------------------------------------------
# 🟩 Footer
# ---------------------------------------------------------
st.markdown("---")
st.caption("Player Profile Dashboard © 2026 — Built with Streamlit + DuckDB + Parquet")
