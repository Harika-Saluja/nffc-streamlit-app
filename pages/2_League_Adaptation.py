import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="League Adaptation", layout="wide")
st.title("League Adaptation")
st.caption(
    "Step 1: Four-factor breakdown for a player's cross-league move — "
    "playing style, teammate ability, league quality, and role fit."
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

has_position = "primary_position" in con.execute("DESCRIBE lineups").df()["column_name"].values
if not has_position:
    st.warning(
        "`primary_position` column not found in lineups.parquet — Factor 4 "
        "(role fit) will show as unavailable until the dataset is rebuilt "
        "with that field."
    )

# -------------------------------
# Base player-season table
# -------------------------------
player_seasons = con.execute("""
    WITH per_match AS (
        SELECT
            l.player_id, l.player_name, l.match_id, l.minutes_played,
            m.season, m.competition,
            COALESCE(e.xg_sum, 0) AS xg_sum,
            e.pass_success_mean,
            COALESCE(e.event_count, 0) AS event_count
        FROM lineups l
        JOIN matches m ON l.match_id = m.match_id
        LEFT JOIN events e ON e.match_id = l.match_id AND e.player_id = l.player_id
    )
    SELECT
        player_id, player_name, season, competition,
        SUM(minutes_played) AS minutes,
        SUM(xg_sum) AS xg_total,
        AVG(pass_success_mean) AS pass_success_avg,
        SUM(event_count) AS events_total
    FROM per_match
    GROUP BY player_id, player_name, season, competition
""").df()

# guard against 0-minute rows before dividing
player_seasons["xg_90"] = np.where(
    player_seasons["minutes"] > 0,
    player_seasons["xg_total"] / player_seasons["minutes"] * 90,
    np.nan,
)
player_seasons["events_90"] = np.where(
    player_seasons["minutes"] > 0,
    player_seasons["events_total"] / player_seasons["minutes"] * 90,
    np.nan,
)

# NOTE: the metric selector used to live here and quietly drove two
# unrelated things further down the page (Factor 3's "league quality"
# number and Panel d's percentile chart) while three other sections
# (Panel a, Factors 1/2/4) always used all three metrics regardless.
# It's been moved down to sit directly above Panel (d), the only place
# it now controls — see that section for the widget itself.
metric_map = {
    "xG per 90": ("xg_90", "xG / 90"),
    "Pass Success %": ("pass_success_avg", "Pass success (mean probability)"),
    "Events per 90": ("events_90", "Events / 90"),
}
# Factor 3 ("league quality") is part of the fixed four-factor
# breakdown, not something the reader should be able to toggle, so it
# now uses a fixed metric rather than following the (now page-scoped)
# selector. xG/90 is the most directly interpretable attacking-output
# proxy for "how strong is this league" among the three options.
QUALITY_METRIC_COL, QUALITY_METRIC_LABEL = metric_map["xG per 90"]

# -------------------------------
# Sidebar – full player roster
# -------------------------------
st.sidebar.title("Player Selector")

players = player_seasons[["player_id", "player_name"]].drop_duplicates().sort_values("player_name")
if players.empty:
    st.error("No players found in lineups.parquet.")
    st.stop()

player_name = st.sidebar.selectbox("Select Player", players["player_name"])
matched = players.loc[players["player_name"] == player_name, "player_id"]
if matched.empty:
    st.error("Selected player not found.")
    st.stop()
player_id = int(matched.iloc[0])

st.markdown("---")
st.header(player_name)

player_data = player_seasons[player_seasons["player_id"] == player_id].sort_values("season")

if player_data.empty:
    st.info(f"No season data available for {player_name}.")
    st.stop()


def detect_league_switch(pdata: pd.DataFrame):
    """First genuine league switch: competition changes between two
    consecutive tracked seasons for this player. Returns None if the
    player never switched leagues within the tracked window."""
    seasons_sorted = sorted(pdata["season"].dropna().unique())
    for i in range(1, len(seasons_sorted)):
        prev_leagues = set(pdata[pdata["season"] == seasons_sorted[i - 1]]["competition"].dropna())
        curr_leagues = set(pdata[pdata["season"] == seasons_sorted[i]]["competition"].dropna())
        if prev_leagues and curr_leagues and not (prev_leagues & curr_leagues):
            return {
                "from_league": list(prev_leagues)[0],
                "to_league": list(curr_leagues)[0],
                "from_season": seasons_sorted[i - 1],
                "to_season": seasons_sorted[i],
            }
    return None


league_switch = detect_league_switch(player_data)

if league_switch is None:
    st.info(
        f"No detected cross-league move for {player_name} in this dataset "
        f"— either they stayed in one league throughout the tracked "
        f"seasons, or the move happened outside this window. Try a "
        f"different player known to have changed leagues (e.g. a recent "
        f"Serie A → Premier League transfer)."
    )
    st.stop()

st.success(
    f"**Detected move:** {league_switch['from_league']} "
    f"({league_switch['from_season']}) → {league_switch['to_league']} "
    f"({league_switch['to_season']})"
)

before = player_data[player_data["season"] == league_switch["from_season"]]
after = player_data[player_data["season"] == league_switch["to_season"]]

# ===========================================================
# FOUR-FACTOR BREAKDOWN
# ===========================================================
st.header("Four-Factor Breakdown")
st.caption(
    "Lightweight proxies inspired by Dinsdale & Gallagher (2022) "
    "'Transfer Portal' and Hong et al. (2025/26) 'EventGPT' — not a full "
    "replication of either (see notes under each factor)."
)

style_cols = ["xg_90", "pass_success_avg", "events_90"]

# --- Factor 1: playing style similarity ---
style_similarity = None
if not before.empty:
    player_style = before[style_cols].iloc[0].fillna(0).values
    league_avg_style = (
        player_seasons[player_seasons["season"] == league_switch["to_season"]][style_cols]
        .mean()
        .fillna(0)
        .values
    )
    if np.linalg.norm(player_style) > 0 and np.linalg.norm(league_avg_style) > 0:
        style_similarity = float(
            np.dot(player_style, league_avg_style)
            / (np.linalg.norm(player_style) * np.linalg.norm(league_avg_style))
        )

# --- Factor 2: teammate/team ability (points-per-game) ---
def team_ppg(pid: int, season: str):
    tm = con.execute(f"""
        SELECT m.home_team, m.away_team, m.home_score, m.away_score, l.team_name
        FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE l.player_id = {pid} AND m.season = '{season}'
    """).df()
    if tm.empty:
        return None
    pts = []
    for _, r in tm.iterrows():
        if r["team_name"] == r["home_team"]:
            gf, ga = r["home_score"], r["away_score"]
        else:
            gf, ga = r["away_score"], r["home_score"]
        pts.append(3 if gf > ga else (1 if gf == ga else 0))
    return float(np.mean(pts)) if pts else None


old_team_ppg = team_ppg(player_id, league_switch["from_season"])
new_team_ppg = team_ppg(player_id, league_switch["to_season"])

# --- Factor 3: league quality proxy ---
def league_quality(competition: str, season: str):
    comp_players = con.execute(f"""
        SELECT DISTINCT l.player_id FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE m.competition = '{competition}' AND m.season = '{season}'
    """).df()["player_id"]
    q = player_seasons[
        (player_seasons["season"] == season) & (player_seasons["player_id"].isin(comp_players))
    ]
    return float(q[QUALITY_METRIC_COL].mean()) if not q.empty and q[QUALITY_METRIC_COL].notna().any() else None


old_league_quality = league_quality(league_switch["from_league"], league_switch["from_season"])
new_league_quality = league_quality(league_switch["to_league"], league_switch["to_season"])

# --- Factor 4: role/position match ---
old_pos_val = new_pos_val = None
if has_position:
    for season_val, target in [
        (league_switch["from_season"], "old"),
        (league_switch["to_season"], "new"),
    ]:
        pos_df = con.execute(f"""
            SELECT primary_position, COUNT(*) AS n FROM lineups l
            JOIN matches m ON l.match_id = m.match_id
            WHERE l.player_id = {player_id} AND m.season = '{season_val}'
              AND primary_position IS NOT NULL
            GROUP BY primary_position ORDER BY n DESC LIMIT 1
        """).df()
        val = pos_df["primary_position"].iloc[0] if not pos_df.empty else None
        if target == "old":
            old_pos_val = val
        else:
            new_pos_val = val

same_position = (old_pos_val == new_pos_val) if (old_pos_val and new_pos_val) else None

# --- display ---
c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "1. Style similarity",
    f"{style_similarity:.2f}" if style_similarity is not None else "—",
    help="Cosine similarity (0-1) between the player's own pre-move style "
         "vector (xG/90, pass success%, events/90) and the new league's "
         "average that season. Higher = more natural stylistic fit.",
)
c2.metric(
    "2. Team ability (PPG)",
    f"{old_team_ppg:.2f} → {new_team_ppg:.2f}"
    if old_team_ppg is not None and new_team_ppg is not None else "—",
    help="Points-per-game of the old team vs. the new team, that season.",
)
c3.metric(
    "3. League quality (proxy)",
    f"{old_league_quality:.2f} → {new_league_quality:.2f}"
    if old_league_quality is not None and new_league_quality is not None else "—",
    help=f"League-wide average {QUALITY_METRIC_LABEL} that season — a rough "
         f"proxy, not a validated strength rating like a true Elo system.",
)
c4.metric(
    "4. Same role?",
    "Yes" if same_position else ("No" if same_position is not None else "—"),
    help=(f"{old_pos_val or '—'} → {new_pos_val or '—'}" if has_position
          else "primary_position not available in lineups.parquet"),
)

st.caption(
    "These are lightweight proxies, not a replication of either cited "
    "paper's original method — Transfer Portal's Elo-style rating system "
    "and EventGPT's learned player embeddings both need infrastructure "
    "this project's data doesn't have."
)

# ===========================================================
# PAPER-STYLE VISUAL PANELS
# Mirrors Dinsdale & Gallagher (2022) Figure 1's four-panel layout,
# adapted to what this project's data can actually support.
# ===========================================================
st.markdown("---")
st.header("Detailed Move Analysis")

all_metric_cols = ["xg_90", "pass_success_avg", "events_90"]
all_metric_labels = {"xg_90": "xG / 90", "pass_success_avg": "Pass Success %", "events_90": "Events / 90"}

panel_a, panel_c = st.columns([2, 1])

# --- Panel (a): multi-metric % change, before vs after ---
with panel_a:
    st.subheader("(a) Predicted Player Performance Change")
    if before.empty or after.empty:
        st.info("Missing before/after data for this move.")
    else:
        pct_rows = []
        for m in all_metric_cols:
            b_val, a_val = before[m].iloc[0], after[m].iloc[0]
            if pd.notna(b_val) and pd.notna(a_val) and b_val != 0:
                pct_change = (a_val - b_val) / abs(b_val) * 100
                pct_rows.append({"metric": all_metric_labels[m], "pct_change": pct_change})

        if pct_rows:
            pct_df = pd.DataFrame(pct_rows)
            bar_colors = ["seagreen" if v >= 0 else "crimson" for v in pct_df["pct_change"]]
            bar_fig = go.Figure(go.Bar(
                x=pct_df["pct_change"], y=pct_df["metric"], orientation="h",
                marker_color=bar_colors,
                text=[f"{v:+.0f}%" for v in pct_df["pct_change"]],
                textposition="outside",
            ))
            bar_fig.add_vline(x=0, line_color="gray")
            bar_fig.update_layout(
                title=f"{player_name} — predicted % change per metric",
                xaxis_title="% change (before → after move)",
                height=300,
            )
            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.info("Not enough non-zero data to compute % change.")

# --- Panel (c): RAG confidence based on data volume ---
with panel_c:
    st.subheader("(c) Data Confidence")

    def rag_status(n_matches: int) -> tuple[str, str]:
        if n_matches >= 15:
            return "🟢", "Green"
        elif n_matches >= 5:
            return "🟡", "Amber"
        else:
            return "🔴", "Red"

    player_matches_before = int(before["minutes"].count()) if not before.empty else 0
    # count real matches (not aggregated rows) for the confidence check
    player_n_matches = con.execute(f"""
        SELECT COUNT(DISTINCT l.match_id) AS n FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE l.player_id = {player_id} AND m.season = '{league_switch['from_season']}'
    """).df()["n"].iloc[0]

    old_league_n = con.execute(f"""
        SELECT COUNT(DISTINCT match_id) AS n FROM matches
        WHERE competition = '{league_switch['from_league']}' AND season = '{league_switch['from_season']}'
    """).df()["n"].iloc[0]

    new_league_n = con.execute(f"""
        SELECT COUNT(DISTINCT match_id) AS n FROM matches
        WHERE competition = '{league_switch['to_league']}' AND season = '{league_switch['to_season']}'
    """).df()["n"].iloc[0]

    for label_txt, n_val, threshold_note in [
        (player_name, player_n_matches, "player's own matches this season"),
        (league_switch["from_league"], old_league_n, "matches in origin league"),
        (league_switch["to_league"], new_league_n, "matches in destination league"),
    ]:
        badge, status_word = rag_status(int(n_val))
        st.write(f"{badge} **{label_txt}**")
        st.caption(f"{int(n_val)} {threshold_note} — {status_word} confidence")

# --- Panel (d): percentile vs. league distribution ---
st.subheader("(d) Where This Player Sits vs. the New League")

panel_d_metric_choice = st.radio(
    "Chart metric (this chart only):",
    ["xG per 90", "Pass Success %", "Events per 90"],
    horizontal=True,
    key="panel_d_metric",
)
col, label = metric_map[panel_d_metric_choice]

dist_data = player_seasons[
    (player_seasons["season"] == league_switch["to_season"])
    & (player_seasons["competition"] == league_switch["to_league"])
][col].dropna()

if len(dist_data) < 5 or after.empty:
    st.info("Not enough players in the destination league/season to build a distribution.")
else:
    player_value = after[col].iloc[0]
    if pd.notna(player_value):
        percentile = float((dist_data < player_value).mean() * 100)

        strip_fig = go.Figure()
        strip_fig.add_trace(go.Box(
            x=dist_data, name=league_switch["to_league"], boxpoints="all",
            jitter=0.6, pointpos=0, marker_color="lightgray", line_color="lightgray",
            fillcolor="rgba(0,0,0,0)",
        ))
        strip_fig.add_trace(go.Scatter(
            x=[player_value], y=[league_switch["to_league"]],
            mode="markers", marker=dict(size=16, color="crimson", symbol="diamond"),
            name=player_name,
        ))
        strip_fig.update_layout(
            title=f"{player_name} — {label} vs. all {league_switch['to_league']} players "
                  f"({league_switch['to_season']}) — {percentile:.0f}th percentile",
            xaxis_title=label, height=250, showlegend=True,
        )
        st.plotly_chart(strip_fig, use_container_width=True)
    else:
        st.info(f"{player_name} has no recorded {label} value after the move to compare.")