import streamlit as st
import duckdb
import plotly.graph_objects as go

# ---------------------------------------------------------
# Page setup
# ---------------------------------------------------------
st.set_page_config(page_title="Player Profile Dashboard", layout="wide")
st.title("Player Profile Dashboard")

# ---------------------------------------------------------
# Connect to in-memory DuckDB and load Parquet files
# ---------------------------------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE events AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE injuries AS SELECT * FROM read_parquet('injuries.parquet');
    CREATE TABLE catapult AS SELECT * FROM read_parquet('catapult.parquet');
""")

st.success("✅ Parquet files loaded successfully!")

# ---------------------------------------------------------
# Sidebar – Player Selector
# ---------------------------------------------------------
players = con.execute("""
    SELECT DISTINCT player_id, player_name
    FROM lineups
    ORDER BY player_name
""").df()

player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.title(f"Player Profile — {player_name}")

# ---------------------------------------------------------
# Player Bio (formatted)
# ---------------------------------------------------------
bio = con.execute(f"""
    SELECT player_id, player_name, birth_date, formations
    FROM lineups
    WHERE player_id = {player_id}
    LIMIT 1
""").df()

st.subheader("🧍 Player Bio")

if not bio.empty:
    bio_data = {
        "Player ID": int(bio["player_id"].iloc[0]),
        "Name": bio["player_name"].iloc[0],
        "Birth Date": bio["birth_date"].iloc[0],
        "Formation": bio["formations"].iloc[0]
    }
    for key, value in bio_data.items():
        st.write(f"**{key}:** {value}")
else:
    st.info("No bio data available.")

# ---------------------------------------------------------
# Injury History
# ---------------------------------------------------------
inj_cols = [col[0] for col in con.execute("DESCRIBE injuries").fetchall()]
id_col = "player_id" if "player_id" in inj_cols else "athlete_id"

inj = con.execute(f"""
    SELECT reason, days_missed, games_missed, "from", "until"
    FROM injuries
    WHERE {id_col} = {player_id}
""").df()

st.subheader("🩺 Injury History")
if not inj.empty:
    st.dataframe(inj)
else:
    st.info("No recorded injuries.")

# ---------------------------------------------------------
# Technical Performance (Events)
# ---------------------------------------------------------
event_cols = [col[0] for col in con.execute("DESCRIBE events").fetchall()]
id_col_events = "player_id" if "player_id" in event_cols else "athlete_id"

tech = con.execute(f"""
    SELECT
        AVG(pass_pass_success_probability) AS pass_success,
        AVG(shot_statsbomb_xg) AS avg_xg,
        SUM(counterpress) AS counterpress_actions,
        SUM(interception_outcome) AS interceptions
    FROM events
    WHERE {id_col_events} = {player_id}
""").df()

st.subheader("🎯 Technical Performance")
st.write(tech)

# ---------------------------------------------------------
# Physical Metrics (Catapult)
# ---------------------------------------------------------
phys_cols = [col[0] for col in con.execute("DESCRIBE catapult").fetchall()]
id_col_phys = "athlete_id" if "athlete_id" in phys_cols else "player_id"

phys = con.execute(f"""
    SELECT
        AVG(v) AS avg_speed,
        MAX(v) AS top_speed,
        AVG(a) AS avg_accel,
        AVG(hr) AS avg_hr,
        AVG(mp) AS avg_metabolic_power
    FROM catapult
    WHERE {id_col_phys} = {player_id}
""").df()

st.subheader("📊 Physical Metrics")
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
    WHERE e.{id_col_events} = {player_id}
    GROUP BY m.match_id, m.home_team, m.away_team, m.match_date
    ORDER BY m.match_date DESC
    LIMIT 5
""").df()

st.subheader("📅 Recent Form (Last 5 Matches)")
st.dataframe(recent)

# ---------------------------------------------------------
# Radar Chart
# ---------------------------------------------------------
def safe_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0

radar_metrics = {
    "Pass Success": safe_float(tech.pass_success),
    "Avg XG": safe_float(tech.avg_xg),
    "Counterpress": safe_float(tech.counterpress_actions),
    "Interceptions": safe_float(tech.interceptions),
    "Top Speed": safe_float(phys.top_speed),
    "Avg Accel": safe_float(phys.avg_accel)
}

fig = go.Figure()
fig.add_trace(go.Scatterpolar(
    r=list(radar_metrics.values()),
    theta=list(radar_metrics.keys()),
    fill='toself',
    name='Player Profile'
))
fig.update_layout(showlegend=False, title=f"Player Radar — {player_name}")

st.subheader("📈 Player Radar Chart")
st.plotly_chart(fig)

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.markdown("---")
st.caption("Player Profile Dashboard © 2026 — Built with Streamlit + DuckDB + Parquet")
