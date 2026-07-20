import streamlit as st
import duckdb
import pandas as pd
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
    CREATE TABLE lineups  AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches  AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events   AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE injuries AS SELECT * FROM read_parquet('injuries.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
    CREATE TABLE catapult AS SELECT * FROM read_parquet('catapult.parquet');
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
# PLAYER SUMMARY
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Player Summary")

summary = con.execute(f"""
    SELECT
        COUNT(DISTINCT match_id) AS matches_played,
        SUM(minutes_played) AS total_minutes
    FROM lineups
    WHERE player_id = {player_id}
""").df()

injury_days = con.execute(f"""
    SELECT COALESCE(SUM(days_missed), 0) AS injury_days
    FROM injuries
    WHERE statsbomb_id = {player_id}
""").df()

col1, col2, col3 = st.columns(3)
col1.metric("Matches Played", int(summary["matches_played"].iloc[0]))
minutes_val = summary["total_minutes"].iloc[0]
col2.metric("Minutes Played", int(minutes_val) if pd.notna(minutes_val) else 0)
col3.metric("Injury Days", int(injury_days["injury_days"].iloc[0]))

# ---------------------------------------------------------
# TECHNICAL PERFORMANCE
# Uses the CURRENT events.parquet schema as-built
# (event_count, xg_sum, pass_success_mean) — no pass/shot/
# defensive-action breakdown, since that needs a rebuild
# we're intentionally not doing right now.
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Technical Performance")

tech = con.execute(f"""
    SELECT
        SUM(event_count) AS total_events,
        SUM(xg_sum) AS total_xg,
        AVG(pass_success_mean) AS avg_pass_success
    FROM events
    WHERE player_id = {player_id}
""").df()

if pd.isna(tech["total_events"].iloc[0]) or tech["total_events"].iloc[0] == 0:
    st.info("No aggregated event data available for this player.")
else:
    avg_pass = tech["avg_pass_success"].iloc[0]
    pass_pct = f"{avg_pass:.0%}" if pd.notna(avg_pass) else "—"
    total_xg = tech["total_xg"].iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Events", int(tech["total_events"].iloc[0]))
    col2.metric("Total xG", round(total_xg, 2) if pd.notna(total_xg) else 0)
    col3.metric("Avg Pass Success", pass_pct)

# ---------------------------------------------------------
# PHYSICAL LOAD (Catapult)
# IMPORTANT: catapult.parquet does not contain a verified
# "distance in metres" column — the x/y position fields were
# dropped during the build. hr/pl/sl/v/a are best-guess
# Catapult abbreviations (heart rate, player load, sprint
# load/distance, velocity, acceleration) NOT yet confirmed
# against Catapult's own data dictionary. Labeled honestly
# below rather than presented as verified metric units.
# Joins via identity_crosswalk since Catapult's athlete_id
# has no direct relationship to StatsBomb's player_id.
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Physical Load (Catapult)")

physical = con.execute(f"""
    SELECT
        AVG(hr_max)  AS hr_max_avg,
        AVG(sl_sum)  AS sl_sum_avg,
        AVG(a_sum)   AS a_sum_avg
    FROM catapult c
    JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id = {player_id}
""").df()

if pd.isna(physical["sl_sum_avg"].iloc[0]):
    st.info("No Catapult data available for this player "
            "(either no sessions recorded, or no identity match "
            "in identity_crosswalk.parquet).")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Avg Max Heart Rate", round(physical["hr_max_avg"].iloc[0], 1))
    col2.metric("Avg Sprint Load (sl)*", round(physical["sl_sum_avg"].iloc[0], 1))
    col3.metric("Avg Acceleration Load (a)*", round(physical["a_sum_avg"].iloc[0], 3))
    st.caption("*Column meanings inferred from Catapult naming conventions, "
               "not yet confirmed against official documentation — treat as "
               "relative/comparative, not verified absolute units.")

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