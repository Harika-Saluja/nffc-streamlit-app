import streamlit as st
import duckdb
import pandas as pd
import plotly.graph_objects as go

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="League Adaptation", layout="wide")
st.title("League Adaptation")
st.caption(
    "H1: Players new to the Premier League show a measurable dip in "
    "performance in their first season compared to established players."
)

st.warning(
    "**Scope note:** the current dataset only covers the Premier League "
    "(2022-23 to 2024-25), not the other top-5 leagues StatsBomb has "
    "available. This page can identify players who are NEW to the PL "
    "within our dataset window — it cannot confirm which league they "
    "came from, so this is a proxy for 'league adaptation', not a "
    "verified foreign-transfer indicator. A player's first tracked "
    "season (2022-23) is excluded from the 'new' flag, since we can't "
    "tell whether they're a genuine debutant or simply outside our "
    "data window (left-censoring)."
)

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
# Build player-season table: minutes, xG90, pass success, first season
# -------------------------------
player_seasons = con.execute("""
    WITH per_match AS (
        SELECT
            l.player_id, l.player_name, l.match_id, l.minutes_played,
            m.season, m.match_date,
            COALESCE(e.xg_sum, 0) AS xg_sum,
            e.pass_success_mean,
            COALESCE(e.event_count, 0) AS event_count
        FROM lineups l
        JOIN matches m ON l.match_id = m.match_id
        LEFT JOIN events e ON e.match_id = l.match_id AND e.player_id = l.player_id
    )
    SELECT
        player_id, player_name, season,
        SUM(minutes_played) AS minutes,
        SUM(xg_sum) AS xg_total,
        AVG(pass_success_mean) AS pass_success_avg,
        SUM(event_count) AS events_total,
        COUNT(DISTINCT match_id) AS matches_played
    FROM per_match
    GROUP BY player_id, player_name, season
""").df()

# per-90 metrics (guard against 0 minutes)
player_seasons["xg_90"] = player_seasons.apply(
    lambda r: (r["xg_total"] / r["minutes"] * 90) if r["minutes"] > 0 else None, axis=1
)
player_seasons["events_90"] = player_seasons.apply(
    lambda r: (r["events_total"] / r["minutes"] * 90) if r["minutes"] > 0 else None, axis=1
)

# each player's first tracked season, and whether this season is "new"
first_season = player_seasons.groupby("player_id")["season"].min().rename("first_season")
player_seasons = player_seasons.merge(first_season, on="player_id")

EARLIEST_DATASET_SEASON = player_seasons["season"].min()  # left-censoring guard
player_seasons["is_new_season"] = (
    (player_seasons["season"] == player_seasons["first_season"])
    & (player_seasons["first_season"] != EARLIEST_DATASET_SEASON)
)

# -------------------------------
# Sidebar – only players who have a valid "new season" flag are
# interesting for this page, but allow anyone for comparison
# -------------------------------
st.sidebar.title("Player Selector")

players = player_seasons[["player_id", "player_name"]].drop_duplicates().sort_values("player_name")
player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(player_name)

player_data = player_seasons[player_seasons["player_id"] == player_id].sort_values("season")

if player_data.empty:
    st.info("No season data available for this player.")
    st.stop()

# -------------------------------
# Per-season trend, first/new season highlighted
# -------------------------------
st.subheader("Performance by Season")

metric_choice = st.radio(
    "Metric:", ["xG per 90", "Pass Success %", "Events per 90"], horizontal=True
)
metric_map = {
    "xG per 90": ("xg_90", "xG / 90"),
    "Pass Success %": ("pass_success_avg", "Pass success (mean probability)"),
    "Events per 90": ("events_90", "Events / 90"),
}
col, label = metric_map[metric_choice]

colors = ["crimson" if new else "steelblue" for new in player_data["is_new_season"]]

fig = go.Figure(go.Bar(
    x=player_data["season"], y=player_data[col],
    marker_color=colors,
    text=[f"{v:.2f}" if pd.notna(v) else "—" for v in player_data[col]],
    textposition="outside",
))
fig.update_layout(
    title=f"{player_name} — {label} by season (red = first PL season, per scope note above)",
    xaxis_title="Season", yaxis_title=label,
)
st.plotly_chart(fig, use_container_width=True)

if not player_data["is_new_season"].any():
    if player_data["first_season"].iloc[0] == EARLIEST_DATASET_SEASON:
        st.info(
            f"{player_name}'s first tracked season is {EARLIEST_DATASET_SEASON} — "
            f"the earliest season in our dataset, so we can't confirm this is "
            f"genuinely their first PL season (left-censored)."
        )
    else:
        st.info(f"{player_name} has no flagged 'new' season in this window.")

# -------------------------------
# Population comparison: new-season players vs. established players,
# for whichever season the selected player's "new" season falls in
# -------------------------------
new_rows = player_data[player_data["is_new_season"]]

if not new_rows.empty:
    st.markdown("---")
    st.subheader("Context: New vs. Established Players That Season")

    target_season = new_rows["season"].iloc[0]
    cohort = player_seasons[
        (player_seasons["season"] == target_season) & (player_seasons["minutes"] >= 90)
    ]  # require at least one full match's worth of minutes to reduce noise

    new_avg = cohort[cohort["is_new_season"]][col].mean()
    established_avg = cohort[~cohort["is_new_season"]][col].mean()

    comp_fig = go.Figure(go.Bar(
        x=["New players", "Established players", player_name],
        y=[new_avg, established_avg, new_rows[col].iloc[0]],
        marker_color=["crimson", "steelblue", "gold"],
        text=[f"{v:.2f}" if pd.notna(v) else "—" for v in [new_avg, established_avg, new_rows[col].iloc[0]]],
        textposition="outside",
    ))
    comp_fig.update_layout(
        title=f"{label} — {target_season}: league-wide comparison",
        yaxis_title=label,
    )
    st.plotly_chart(comp_fig, use_container_width=True)

    st.caption(
        f"'New players' = players whose first tracked season is {target_season} "
        f"(excludes {EARLIEST_DATASET_SEASON} debutants, per scope note). "
        f"Minimum 90 minutes played to reduce small-sample noise. This is a "
        f"single-season snapshot, not the full statistical test — the formal "
        f"H1 verdict (significance test across all seasons/players) should be "
        f"computed separately and shown on the Myth Verdict page."
    )