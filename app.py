import streamlit as st
import duckdb
import os

# ---------------------------------------------------------
# SAFETY CHECK — MUST BE AT THE TOP
# ---------------------------------------------------------
st.title("Player Profile Dashboard")

db_path = "nffc.duckdb"

# If file is missing
if not os.path.exists(db_path):
    st.error("❌ Database file not found in the deployed app.")
    st.stop()

# If file exists but cannot be opened
try:
    con = duckdb.connect(db_path)
except Exception as e:
    st.error(f"❌ Could not open DuckDB file: {e}")
    st.info("This usually happens because the file is too large for Streamlit Cloud.")
    st.stop()

# ---------------------------------------------------------
# Sidebar – Player Selector
# ---------------------------------------------------------
st.sidebar.title("Player Profile Dashboard")

players = con.execute("""
    SELECT DISTINCT player_id, player_name
    FROM lineups
    ORDER BY player_name
""").df()

player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players[players["player_name"] == player_name]["player_id"].iloc[0])

st.title(f"Player Profile — {player_name}")

# ---------------------------------------------------------
# Player Bio
# ---------------------------------------------------------
bio = con.execute(f"""
    SELECT player_id, player_name, birth_date, positions
    FROM lineups
    WHERE player_id = {player_id}
    LIMIT 1
""").df()
st.subheader("Player Bio")
st.write(bio)

# ---------------------------------------------------------
# Injury History
# ---------------------------------------------------------
inj = con.execute(f"""
    SELECT reason, days_missed, games_missed, "from", "until"
    FROM injuries
    WHERE player_id = {player_id}
""").df()
st.subheader("🩺 Injury History")
st.dataframe(inj) if not inj.empty else st.info("No recorded injuries.")

# ---------------------------------------------------------
# Technical Performance
# ---------------------------------------------------------
tech = con.execute(f"""
    SELECT
        AVG(pass_pass_success_probability) AS pass_success,
        AVG(shot_statsbomb_xg) AS avg_xg,
        SUM(counterpress) AS counterpress_actions,
        SUM(interception_outcome) AS interceptions
    FROM events
    WHERE player_id = {player_id}
""").df()
st.subheader("Technical Performance")
st.write(tech)

# ---------------------------------------------------------
# Physical Metrics (Catapult)
# ---------------------------------------------------------
phys = con.execute(f"""
    SELECT
        AVG(v) AS avg_speed,
        MAX(v) AS top_speed,
        AVG(a) AS avg_accel,
        AVG(hr) AS avg_hr,
        AVG(mp) AS avg_metabolic_power
    FROM catapult
    WHERE athlete_id = {player_id}
""").df()
st.subheader("Physical Metrics")
st.write(phys)

# ---------------------------------------------------------
# Recent Form (Last 5 Matches)
# ---------------------------------------------------------
recent = con.execute(f"""
    SELECT
        m.match_id,
        m.home_team,
        m.away_team,
        m.match_date,
        AVG(e.pass_pass_success_probability) AS pass_success,
        SUM(e.shot_statsbomb_xg) AS xg,
        SUM(e.counterpress) AS counterpress,
        SUM(e.interception_outcome) AS interceptions
    FROM matches m
    LEFT JOIN events e ON m.match_id = e.match_id
    WHERE e.player_id = {player_id}
    GROUP BY m.match_id, m.home_team, m.away_team, m.match_date
    ORDER BY m.match_date DESC
    LIMIT 5
""").df()
st.subheader("Recent Form (Last 5 Matches)")
st.dataframe(recent)

# ---------------------------------------------------------
# Radar Chart
# ---------------------------------------------------------
radar_metrics = {
    "Pass Success": float(tech.pass_success),
    "Avg XG": float(tech.avg_xg),
    "Counterpress": float(tech.counterpress_actions),
    "Interceptions": float(tech.interceptions),
    "Top Speed": float(phys.top_speed),
    "Avg Accel": float(phys.avg_accel)
}

fig = go.Figure()
fig.add_trace(go.Scatterpolar(
    r=list(radar_metrics.values()),
    theta=list(radar_metrics.keys()),
    fill='toself',
    name='Player Profile'
))
fig.update_layout(showlegend=False, title=f"Player Radar — {player_name}")

st.subheader("Player Radar Chart")
st.plotly_chart(fig)
