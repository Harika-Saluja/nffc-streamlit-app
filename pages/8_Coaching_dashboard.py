import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
import os

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Training & Coaching Dashboard", layout="wide")
st.title("Training & Coaching Dashboard")
st.caption(
    "A day-to-day readiness view for coaching staff: is this player "
    "currently available, how loaded are they, and how has recent form "
    "looked. Built on the same Catapult/injury data as the Workload & "
    "Injury Risk hypothesis page, but framed around one player's current "
    "status rather than population-level statistics."
)
st.warning(
    "**This uses historical data, not a live feed.** 'Current' below means "
    "'as of this player's most recent recorded session/match in the "
    "dataset', not today's real-world date. In a production version this "
    "would connect to a live data feed."
)

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups   AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches   AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events    AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE injuries  AS SELECT * FROM read_parquet('injuries.parquet');
    CREATE TABLE catapult  AS SELECT * FROM read_parquet('catapult.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
""")

# -------------------------------
# Sidebar – only players with Catapult data, since the whole
# readiness snapshot depends on it
# -------------------------------
st.sidebar.title("Player Selector")

players_with_load = con.execute("""
    SELECT DISTINCT l.player_id, l.player_name
    FROM lineups l
    JOIN crosswalk x ON l.player_id = x.statsbomb_player_id
    JOIN catapult c ON c.athlete_id = x.athlete_id
    ORDER BY l.player_name
""").df()

if players_with_load.empty:
    st.error("No players could be matched via identity_crosswalk.parquet.")
    st.stop()

player_name = st.sidebar.selectbox("Select Player", players_with_load["player_name"])
player_id = int(
    players_with_load.loc[players_with_load["player_name"] == player_name, "player_id"].iloc[0]
)

LOAD_METRIC = st.sidebar.radio(
    "Load metric for ACWR:",
    ["Player Load (pl_sum)", "Sprint Load (sl_sum)", "Acceleration Load (a_sum)"],
)
load_metric_map = {
    "Player Load (pl_sum)": "pl_sum",
    "Sprint Load (sl_sum)": "sl_sum",
    "Acceleration Load (a_sum)": "a_sum",
}
load_col = load_metric_map[LOAD_METRIC]

st.markdown("---")
st.header(player_name)

# -------------------------------
# Pull this player's sessions and injuries
# -------------------------------
sessions = con.execute(f"""
    SELECT c.date, c.{load_col} AS load_value
    FROM catapult c
    JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id = {player_id}
    ORDER BY c.date
""").df()

player_injuries = con.execute(f"""
    SELECT reason, "from" AS injury_start, until AS injury_end, days_missed
    FROM injuries
    WHERE statsbomb_id = {player_id}
    ORDER BY "from"
""").df()

if sessions.empty:
    st.info(f"No Catapult sessions found for {player_name}.")
    st.stop()

sessions["date"] = pd.to_datetime(sessions["date"])
if not player_injuries.empty:
    player_injuries["injury_start"] = pd.to_datetime(player_injuries["injury_start"])
    player_injuries["injury_end"] = pd.to_datetime(player_injuries["injury_end"])

as_of_date = sessions["date"].max()
st.caption(f"Data as of: **{as_of_date.date()}** (this player's most recent recorded session)")

# ===========================================================
# 1. AVAILABILITY STATUS
# ===========================================================
st.subheader("Current Availability")

active_injury = player_injuries[
    (player_injuries["injury_start"] <= as_of_date) & (player_injuries["injury_end"] >= as_of_date)
] if not player_injuries.empty else pd.DataFrame()

if not active_injury.empty:
    row = active_injury.iloc[0]
    st.error(
        f"🔴 **UNAVAILABLE** — {row['reason'] if pd.notna(row['reason']) else 'injury'} "
        f"since {row['injury_start'].date()}, expected return {row['injury_end'].date()} "
        f"({row['days_missed']} days missed)."
    )
else:
    st.success("🟢 **AVAILABLE** — no active injury as of the most recent recorded date.")

# ===========================================================
# 2. READINESS SNAPSHOT — ACWR
# ===========================================================
st.markdown("---")
st.subheader("Readiness Snapshot — Acute:Chronic Workload Ratio (ACWR)")

st.caption(
    "ACWR compares a player's average daily load over the last 7 days "
    "(acute) to their average daily load over the last 28 days (chronic). "
    "A widely cited sports-science guideline (Gabbett et al.) treats "
    "0.8–1.3 as a normal/safe loading zone, 1.3–1.5 as a caution zone, "
    "and >1.5 as a 'spike' associated with higher injury risk in the "
    "literature. Below 0.8 can indicate undertraining/detraining."
)


def compute_acwr(sessions: pd.DataFrame, as_of: pd.Timestamp, load_col: str = "load_value"):
    acute_window = sessions[(sessions["date"] > as_of - pd.Timedelta(days=7)) & (sessions["date"] <= as_of)]
    chronic_window = sessions[(sessions["date"] > as_of - pd.Timedelta(days=28)) & (sessions["date"] <= as_of)]

    acute_avg = acute_window[load_col].sum() / 7
    chronic_avg = chronic_window[load_col].sum() / 28

    if chronic_avg == 0:
        return None, acute_avg, chronic_avg
    return acute_avg / chronic_avg, acute_avg, chronic_avg


acwr, acute_avg, chronic_avg = compute_acwr(sessions, as_of_date, "load_value")

if acwr is None:
    st.info("Not enough training history (28+ days) to compute ACWR yet.")
else:
    if acwr < 0.8:
        zone, zone_color = "Undertrained", "orange"
    elif acwr <= 1.3:
        zone, zone_color = "Safe / Normal", "green"
    elif acwr <= 1.5:
        zone, zone_color = "Caution", "gold"
    else:
        zone, zone_color = "High Risk (Spike)", "red"

    gauge_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=acwr,
        number={"suffix": "", "valueformat": ".2f"},
        gauge={
            "axis": {"range": [0, 2.5]},
            "bar": {"color": zone_color},
            "steps": [
                {"range": [0, 0.8], "color": "#fde8d0"},
                {"range": [0.8, 1.3], "color": "#d4f0d4"},
                {"range": [1.3, 1.5], "color": "#fdf3d0"},
                {"range": [1.5, 2.5], "color": "#f8d0d0"},
            ],
            "threshold": {"line": {"color": "black", "width": 3}, "thickness": 0.8, "value": acwr},
        },
        title={"text": f"ACWR — {LOAD_METRIC}"},
    ))
    st.plotly_chart(gauge_fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("ACWR", f"{acwr:.2f}")
    c2.metric("Zone", zone)
    c3.metric("7d avg / 28d avg", f"{acute_avg:.1f} / {chronic_avg:.1f}")

    # tie back to the actual H2 population verdict, if computed
    h2_verdict = None
    if os.path.exists("verdict_h2.json"):
        with open("verdict_h2.json") as f:
            h2_verdict = json.load(f)

    if zone in ("Caution", "High Risk (Spike)"):
        msg = (
            f"⚠️ {player_name}'s current load is in the **{zone}** zone."
        )
        if h2_verdict:
            msg += (
                f" The population-level H2 test (Workload & Injury Risk page) "
                f"found a verdict of **{h2_verdict['test_2']['verdict']}** for "
                f"load predicting injury odds — worth reviewing that page for "
                f"the full population context before making a training decision."
            )
        st.warning(msg)
    else:
        st.success(f"{player_name}'s current load is in the **{zone}** zone.")

# ===========================================================
# 3. RECENT FORM
# ===========================================================
st.markdown("---")
st.subheader("Recent Form (Last 10 Matches)")

recent_form = con.execute(f"""
    SELECT m.match_date, e.xg_sum, e.pass_success_mean, e.event_count
    FROM events e
    JOIN matches m ON e.match_id = m.match_id
    WHERE e.player_id = {player_id}
    ORDER BY m.match_date DESC
    LIMIT 10
""").df().sort_values("match_date")

if recent_form.empty:
    st.info("No recent match event data available for this player.")
else:
    form_fig = go.Figure()
    form_fig.add_trace(go.Scatter(
        x=recent_form["match_date"], y=recent_form["xg_sum"],
        mode="lines+markers", name="xG",
    ))
    form_fig.update_layout(
        title=f"{player_name} — xG, last {len(recent_form)} matches",
        xaxis_title="Match Date", yaxis_title="xG",
    )
    st.plotly_chart(form_fig, use_container_width=True)

# ===========================================================
# 4. TRAINING LOG
# ===========================================================
st.markdown("---")
st.subheader("Training Log (Last 14 Sessions)")

# compute a rolling ACWR series across the player's whole history,
# so we can flag which recent sessions pushed into a risk zone
daily_acwr = []
for _, row in sessions.iterrows():
    r, _, _ = compute_acwr(sessions, row["date"], "load_value")
    daily_acwr.append(r)
sessions["acwr"] = daily_acwr


def flag_zone(r):
    if r is None:
        return "—"
    if r < 0.8:
        return "🟠 Undertrained"
    if r <= 1.3:
        return "🟢 Safe"
    if r <= 1.5:
        return "🟡 Caution"
    return "🔴 Spike"


sessions["flag"] = sessions["acwr"].apply(flag_zone)

log_table = sessions.tail(14)[["date", "load_value", "acwr", "flag"]].sort_values("date", ascending=False)
log_table = log_table.rename(columns={"load_value": LOAD_METRIC, "acwr": "ACWR"})
log_table["ACWR"] = log_table["ACWR"].round(2)
log_table[LOAD_METRIC] = log_table[LOAD_METRIC].round(1)

st.dataframe(log_table, use_container_width=True, hide_index=True)

st.caption(
    "Column meanings (pl, sl, a) are inferred from Catapult naming "
    "conventions, not yet confirmed against official documentation — "
    "treat as relative/comparative, not verified absolute units."
)