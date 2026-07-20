import streamlit as st
import duckdb
import pandas as pd
import plotly.graph_objects as go

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Workload & Injury Risk", layout="wide")
st.title("Workload & Injury Risk")
st.caption(
    "H2: Higher physical load in the period before an injury is associated "
    "with increased injury likelihood. Uses Catapult training-load data "
    "joined to injury records via the identity crosswalk."
)

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups   AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE injuries  AS SELECT * FROM read_parquet('injuries.parquet');
    CREATE TABLE catapult  AS SELECT * FROM read_parquet('catapult.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
""")

# -------------------------------
# Sidebar – only show players who actually have Catapult data,
# so the page never lands on a silent "no data" default
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
    st.error(
        "No players could be matched between Catapult and lineup data via "
        "identity_crosswalk.parquet. Check that the crosswalk was built "
        "successfully before using this page."
    )
    st.stop()

player_name = st.sidebar.selectbox("Select Player", players_with_load["player_name"])
player_id = int(
    players_with_load.loc[players_with_load["player_name"] == player_name, "player_id"].iloc[0]
)

st.markdown("---")
st.header(player_name)

# -------------------------------
# Pull this player's workload sessions and injury spells
# -------------------------------
load_df = con.execute(f"""
    SELECT c.date, c.hr_max, c.sl_sum, c.a_sum, c.pl_sum
    FROM catapult c
    JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id = {player_id}
    ORDER BY c.date
""").df()

injury_df = con.execute(f"""
    SELECT reason, "from" AS injury_start, until AS injury_end,
           days_missed, games_missed
    FROM injuries
    WHERE statsbomb_id = {player_id}
    ORDER BY "from"
""").df()

if load_df.empty:
    st.info("No Catapult sessions found for this player.")
    st.stop()

load_df["date"] = pd.to_datetime(load_df["date"])
if not injury_df.empty:
    injury_df["injury_start"] = pd.to_datetime(injury_df["injury_start"])
    injury_df["injury_end"] = pd.to_datetime(injury_df["injury_end"])

# -------------------------------
# Workload trend with injury periods shaded
# -------------------------------
st.subheader("Training Load Over Time")

metric_choice = st.radio(
    "Load metric:",
    ["Sprint Load (sl_sum)", "Acceleration Load (a_sum)",
     "Player Load (pl_sum)", "Max Heart Rate (hr_max)"],
    horizontal=True,
)
metric_map = {
    "Sprint Load (sl_sum)": "sl_sum",
    "Acceleration Load (a_sum)": "a_sum",
    "Player Load (pl_sum)": "pl_sum",
    "Max Heart Rate (hr_max)": "hr_max",
}
col = metric_map[metric_choice]

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=load_df["date"], y=load_df[col],
    mode="lines+markers", name=metric_choice,
))

# shade each injury period on top of the load trend
for _, row in injury_df.iterrows():
    fig.add_vrect(
        x0=row["injury_start"], x1=row["injury_end"],
        fillcolor="red", opacity=0.15, line_width=0,
        annotation_text=row["reason"] if pd.notna(row["reason"]) else "Injury",
        annotation_position="top left",
    )

fig.update_layout(
    title=f"{player_name} — {metric_choice} (red = injury period)",
    xaxis_title="Date", yaxis_title=metric_choice,
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Column meanings (hr, sl, a, pl) are inferred from Catapult naming "
    "conventions and not yet confirmed against official documentation — "
    "treat as relative/comparative, not verified absolute units."
)

# -------------------------------
# Pre-injury load vs. season-average load
# Simple, transparent comparison for this one player — NOT a
# population-level statistical test. That belongs in a separate
# offline script feeding the Myth Verdict page (logistic
# regression across all players), not computed live per-click here.
# -------------------------------
st.markdown("---")
st.subheader("Pre-Injury Load Check")

WINDOW_DAYS = st.slider("Look-back window before injury (days)", 3, 28, 14)

if injury_df.empty:
    st.info("No injury records for this player — nothing to compare.")
else:
    season_avg = load_df[col].mean()
    rows = []
    for _, row in injury_df.iterrows():
        window_start = row["injury_start"] - pd.Timedelta(days=WINDOW_DAYS)
        pre_injury = load_df[
            (load_df["date"] >= window_start) & (load_df["date"] < row["injury_start"])
        ]
        rows.append({
            "Injury": row["reason"] if pd.notna(row["reason"]) else "Unspecified",
            "Date": row["injury_start"].date(),
            "Days Missed": row["days_missed"],
            f"Avg {metric_choice} ({WINDOW_DAYS}d before)": (
                round(pre_injury[col].mean(), 2) if not pre_injury.empty else None
            ),
            "Season Avg": round(season_avg, 2),
        })

    result_df = pd.DataFrame(rows)
    st.dataframe(result_df, use_container_width=True)

    st.caption(
        "Compares this player's average load in the window before each "
        "injury to their season average. Higher pre-injury values are "
        "consistent with H2, but a single player's data is not statistical "
        "evidence — the population-level test (across all players) should "
        "be run separately and shown on the Myth Verdict page."
    )