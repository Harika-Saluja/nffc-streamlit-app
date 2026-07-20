import streamlit as st
import duckdb
import plotly.express as px

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Player Profile Dashboard", layout="wide")

st.title("Player Profile")

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events  AS SELECT * FROM read_parquet('events.parquet');
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
st.header(f"{player_name}")

# -------------------------------
# Player bio
# -------------------------------
bio = con.execute(f"""
    SELECT player_id, player_name, team_name, birth_date, minutes_played
    FROM lineups
    WHERE player_id = {player_id}
    LIMIT 1
""").df()

if bio.empty:
    st.info("No bio data available for this player.")
else:
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Player ID:** {int(bio['player_id'].iloc[0])}")
        st.write(f"**Birth Date:** {bio['birth_date'].iloc[0]}")
    with col2:
        st.write(f"**Team:** {bio['team_name'].iloc[0]}")

# ---------------------------------------------------------
# PERFORMANCE TREND
# Native Streamlit + Plotly — no Power BI/Grafana embedding
# needed. End users never see this is Python; it renders as
# an ordinary interactive web chart, same as any BI tool would.
# ---------------------------------------------------------
st.markdown("---")
st.header("Performance Trend")

trend = con.execute(f"""
    SELECT
        m.match_date,
        m.season,
        e.xg_sum,
        e.pass_success_mean,
        e.event_count
    FROM events e
    JOIN matches m ON e.match_id = m.match_id
    WHERE e.player_id = {player_id}
    ORDER BY m.match_date
""").df()

if trend.empty:
    st.info("No match event data available for this player.")
else:
    metric_choice = st.radio(
        "Show:",
        ["Expected Goals (xG)", "Pass Success %", "Involvement (event count)"],
        horizontal=True,
    )
    metric_map = {
        "Expected Goals (xG)": ("xg_sum", "xG per match"),
        "Pass Success %": ("pass_success_mean", "Pass success (mean probability)"),
        "Involvement (event count)": ("event_count", "Events per match"),
    }
    col, label = metric_map[metric_choice]

    fig = px.line(
        trend, x="match_date", y=col,
        markers=True,
        title=f"{player_name} — {label} over time",
        labels={"match_date": "Match Date", col: label},
    )
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # simple rolling average overlay — easier for a non-technical
    # viewer to read the trend through match-to-match noise
    trend["rolling_avg"] = trend[col].rolling(5, min_periods=1).mean()
    fig2 = px.line(
        trend, x="match_date", y="rolling_avg",
        title=f"{player_name} — {label} (5-match rolling average)",
        labels={"match_date": "Match Date", "rolling_avg": f"{label} (rolling avg)"},
    )
    st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------
# VERDICT SUMMARY (4 finalized hypotheses)
# Labels updated: H1 "Adaptation Tax" -> "League Adaptation",
# H2 "Transfer Timing" -> "Workload & Injury Risk" (the two
# transfer-fee/contract hypotheses were dropped for lack of
# data; see prior discussion).
# ---------------------------------------------------------
st.markdown("---")
st.header("Verdict Summary")

st.write("### Hypothesis 1: League Adaptation")
st.write("*(Result will be added here — verdicts.parquet not yet built)*")

st.write("### Hypothesis 2: Workload & Injury Risk")
st.write("*(Result will be added here)*")

st.write("### Hypothesis 3: Age Optimization")
st.write("*(Result will be added here)*")

st.write("### Hypothesis 4: Squad Balance")
st.write("*(Result will be added here)*")

# ---------------------------------------------------------
# PERFECT SIGNING SCORE (placeholder)
# ---------------------------------------------------------
st.markdown("---")
st.header("Perfect Signing Score")
st.write("*(Gauge chart will be added here)*")
st.empty()