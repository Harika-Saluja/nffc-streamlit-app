import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
import json
from datetime import datetime, timezone

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="League Adaptation", layout="wide")
st.title("League Adaptation")
st.caption(
    "H1: Players who move to a new league show a measurable dip in "
    "performance immediately after the move, before adapting to their new "
    "league's physical, tactical, and competitive demands."
)
st.warning(
    "**This page tests genuine cross-league moves only** — a player whose "
    "`competition` value changes between consecutive tracked seasons "
    "(e.g. Serie A → Premier League). It no longer uses a 'new to our "
    "dataset' proxy: with the full 5-league rebuild, real cross-league "
    "detection is possible, so that's what's tested directly."
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

has_country = "country" in con.execute("DESCRIBE lineups").df()["column_name"].values
has_position = "primary_position" in con.execute("DESCRIBE lineups").df()["column_name"].values

# -------------------------------
# Base player-season table: minutes, xG90, pass success, league per season
# -------------------------------
player_seasons = con.execute("""
    WITH per_match AS (
        SELECT
            l.player_id, l.player_name, l.match_id, l.minutes_played,
            m.season, m.match_date, m.competition,
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
        SUM(event_count) AS events_total,
        COUNT(DISTINCT match_id) AS matches_played
    FROM per_match
    GROUP BY player_id, player_name, season, competition
""").df()

player_seasons["xg_90"] = player_seasons.apply(
    lambda r: (r["xg_total"] / r["minutes"] * 90) if r["minutes"] > 0 else None, axis=1
)
player_seasons["events_90"] = player_seasons.apply(
    lambda r: (r["events_total"] / r["minutes"] * 90) if r["minutes"] > 0 else None, axis=1
)

metric_choice = st.radio(
    "Metric:", ["xG per 90", "Pass Success %", "Events per 90"], horizontal=True
)
metric_map = {
    "xG per 90": ("xg_90", "xG / 90"),
    "Pass Success %": ("pass_success_avg", "Pass success (mean probability)"),
    "Events per 90": ("events_90", "Events / 90"),
}
col, label = metric_map[metric_choice]

# -------------------------------
# Sidebar – full player roster
# -------------------------------
st.sidebar.title("Player Selector")

players = player_seasons[["player_id", "player_name"]].drop_duplicates().sort_values("player_name")
player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(player_name)


def detect_league_switch(pdata: pd.DataFrame):
    """For one player's season-by-season data, find the first genuine
    league switch (competition changes between consecutive seasons)."""
    seasons_sorted = sorted(pdata["season"].unique())
    for i in range(1, len(seasons_sorted)):
        prev_leagues = set(pdata[pdata["season"] == seasons_sorted[i - 1]]["competition"])
        curr_leagues = set(pdata[pdata["season"] == seasons_sorted[i]]["competition"])
        if prev_leagues and curr_leagues and not (prev_leagues & curr_leagues):
            return {
                "from_league": list(prev_leagues)[0], "to_league": list(curr_leagues)[0],
                "from_season": seasons_sorted[i - 1], "to_season": seasons_sorted[i],
            }
    return None


player_data = player_seasons[player_seasons["player_id"] == player_id].sort_values("season")
league_switch = detect_league_switch(player_data) if not player_data.empty else None

# ===========================================================
# SELECTED PLAYER: move detection + before/after + four factors
# ===========================================================
if league_switch is None:
    st.info(
        f"No detected cross-league move for {player_name} in this dataset "
        f"— either they stayed in one league throughout the tracked "
        f"seasons, or their move happened outside this window."
    )
else:
    st.success(
        f"**Detected move:** {league_switch['from_league']} "
        f"({league_switch['from_season']}) → {league_switch['to_league']} "
        f"({league_switch['to_season']})"
    )

    before = player_data[player_data["season"] == league_switch["from_season"]]
    after = player_data[player_data["season"] == league_switch["to_season"]]

    if not before.empty and not after.empty:
        st.subheader("Performance Change After the Move")
        before_val, after_val = before[col].iloc[0], after[col].iloc[0]
        delta = after_val - before_val if pd.notna(before_val) and pd.notna(after_val) else None

        move_fig = go.Figure(go.Bar(
            x=[f"Before ({league_switch['from_league']})", f"After ({league_switch['to_league']})"],
            y=[before_val, after_val],
            marker_color=["steelblue", "crimson" if (delta or 0) < 0 else "seagreen"],
            text=[f"{v:.2f}" if pd.notna(v) else "—" for v in [before_val, after_val]],
            textposition="outside",
        ))
        move_fig.update_layout(title=f"{player_name} — {label}: before vs. after the move", yaxis_title=label)
        st.plotly_chart(move_fig, use_container_width=True)

        if delta is not None:
            direction = "improved" if delta > 0 else "declined"
            st.metric(f"Change ({direction})", f"{delta:+.2f}")

    # --- four-factor breakdown (Dinsdale & Gallagher, 2022 framing) ---
    st.subheader("Four-Factor Breakdown")
    st.caption(
        "Lightweight proxies inspired by Dinsdale & Gallagher (2022) "
        "'Transfer Portal' and Hong et al. (2025/26) 'EventGPT' — not a "
        "replication of either (see page notes below for what couldn't "
        "be reproduced)."
    )

    style_cols = ["xg_90", "pass_success_avg", "events_90"]
    player_style = before[style_cols].iloc[0].fillna(0).values if not before.empty else None
    league_avg_style = player_seasons[
        player_seasons["season"] == league_switch["to_season"]
    ][style_cols].mean().fillna(0).values

    style_similarity = None
    if player_style is not None and np.linalg.norm(player_style) > 0 and np.linalg.norm(league_avg_style) > 0:
        style_similarity = float(
            np.dot(player_style, league_avg_style)
            / (np.linalg.norm(player_style) * np.linalg.norm(league_avg_style))
        )

    def team_ppg(pid, season):
        tm = con.execute(f"""
            SELECT m.home_team, m.away_team, m.home_score, m.away_score, l.team_name
            FROM lineups l JOIN matches m ON l.match_id = m.match_id
            WHERE l.player_id = {pid} AND m.season = '{season}'
        """).df()
        if tm.empty:
            return None
        pts = []
        for _, r in tm.iterrows():
            gf, ga = (r["home_score"], r["away_score"]) if r["team_name"] == r["home_team"] \
                else (r["away_score"], r["home_score"])
            pts.append(3 if gf > ga else (1 if gf == ga else 0))
        return np.mean(pts) if pts else None

    old_team_ppg = team_ppg(player_id, league_switch["from_season"])
    new_team_ppg = team_ppg(player_id, league_switch["to_season"])

    def league_quality(competition, season):
        comp_players = con.execute(f"""
            SELECT DISTINCT l.player_id FROM lineups l JOIN matches m ON l.match_id = m.match_id
            WHERE m.competition = '{competition}' AND m.season = '{season}'
        """).df()["player_id"]
        q = player_seasons[
            (player_seasons["season"] == season) & (player_seasons["player_id"].isin(comp_players))
        ]
        return q[col].mean() if not q.empty else None

    old_league_quality = league_quality(league_switch["from_league"], league_switch["from_season"])
    new_league_quality = league_quality(league_switch["to_league"], league_switch["to_season"])

    old_pos_val = new_pos_val = None
    if has_position:
        for label_pos, season_val, var_name in [
            ("old", league_switch["from_season"], "old_pos_val"),
            ("new", league_switch["to_season"], "new_pos_val"),
        ]:
            pos_df = con.execute(f"""
                SELECT primary_position, COUNT(*) AS n FROM lineups l
                JOIN matches m ON l.match_id = m.match_id
                WHERE l.player_id = {player_id} AND m.season = '{season_val}'
                GROUP BY primary_position ORDER BY n DESC LIMIT 1
            """).df()
            val = pos_df["primary_position"].iloc[0] if not pos_df.empty else None
            if var_name == "old_pos_val":
                old_pos_val = val
            else:
                new_pos_val = val
    same_position = (old_pos_val == new_pos_val) if old_pos_val and new_pos_val else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("1. Style similarity", f"{style_similarity:.2f}" if style_similarity is not None else "—",
              help="Cosine similarity (0-1) between the player's own style vector and the new league's average.")
    c2.metric("2. Team ability (PPG)",
              f"{old_team_ppg:.2f} → {new_team_ppg:.2f}" if old_team_ppg is not None and new_team_ppg is not None else "—",
              help="Points-per-game of old team vs. new team that season.")
    c3.metric("3. League quality (proxy)",
              f"{old_league_quality:.2f} → {new_league_quality:.2f}" if old_league_quality is not None and new_league_quality is not None else "—",
              help=f"League-wide average {label} — a rough proxy, not a validated strength rating.")
    c4.metric("4. Same role?", "Yes" if same_position else ("No" if same_position is not None else "—"),
              help=f"{old_pos_val or '—'} → {new_pos_val or '—'}" if has_position else "primary_position not available")

    # --- suggested replacements ---
    st.subheader(f"Suggested Replacements in {league_switch['from_league']}")
    if has_position and old_pos_val is not None and player_style is not None:
        candidates = con.execute(f"""
            SELECT DISTINCT l.player_id, l.player_name FROM lineups l
            JOIN matches m ON l.match_id = m.match_id
            WHERE m.competition = '{league_switch['from_league']}'
              AND m.season = '{league_switch['from_season']}'
              AND l.primary_position = '{old_pos_val}'
              AND l.player_id != {player_id}
        """).df()
        sims = []
        for _, cand in candidates.iterrows():
            cand_row = player_seasons[
                (player_seasons["player_id"] == cand["player_id"])
                & (player_seasons["season"] == league_switch["from_season"])
            ]
            if cand_row.empty:
                continue
            cand_style = cand_row[style_cols].iloc[0].fillna(0).values
            if np.linalg.norm(cand_style) == 0:
                continue
            sim = float(np.dot(player_style, cand_style) / (np.linalg.norm(player_style) * np.linalg.norm(cand_style)))
            sims.append({"Player": cand["player_name"], "Style Similarity": round(sim, 3)})
        if sims:
            st.dataframe(pd.DataFrame(sims).sort_values("Style Similarity", ascending=False).head(5),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No comparable players found for a replacement suggestion.")
    else:
        st.info("Position data not available — replacement suggestions need `primary_position` in lineups.parquet.")

# ===========================================================
# POPULATION-LEVEL VERDICT — every genuine cross-league move,
# tested with a paired Wilcoxon signed-rank test (before vs.
# after, per player). This directly tests real transfers now
# that full 5-league data exists, replacing the earlier
# "new to our single-league dataset" proxy entirely.
# ===========================================================
st.markdown("---")
st.header("H1 Statistical Verdict — All Detected Cross-League Moves")

st.caption(
    "Every player in the dataset who genuinely switched leagues between "
    "consecutive tracked seasons is included here — not just the selected "
    "player above. Paired Wilcoxon signed-rank test: does performance "
    "systematically change (in either direction) immediately after a "
    "cross-league move?"
)


@st.cache_data
def build_all_moves(_player_seasons: pd.DataFrame, metric_col: str) -> pd.DataFrame:
    moves = []
    for pid, grp in _player_seasons.groupby("player_id"):
        switch = detect_league_switch(grp)
        if switch is None:
            continue
        before_row = grp[grp["season"] == switch["from_season"]]
        after_row = grp[grp["season"] == switch["to_season"]]
        if before_row.empty or after_row.empty:
            continue
        b, a = before_row[metric_col].iloc[0], after_row[metric_col].iloc[0]
        if pd.isna(b) or pd.isna(a):
            continue
        moves.append({
            "player_id": pid, "player_name": grp["player_name"].iloc[0],
            "from_league": switch["from_league"], "to_league": switch["to_league"],
            "before": b, "after": a,
        })
    return pd.DataFrame(moves)


all_moves = build_all_moves(player_seasons, col)

verdict1 = "NOT COMPUTED"
w_pval = None
median_delta = None

if len(all_moves) < 10:
    st.warning(
        f"Only {len(all_moves)} cross-league moves detected in this dataset "
        f"— not enough to run the test reliably."
    )
else:
    w_stat, w_pval = stats.wilcoxon(all_moves["before"], all_moves["after"])
    all_moves["delta"] = all_moves["after"] - all_moves["before"]
    median_delta = all_moves["delta"].median()

    box_fig = go.Figure()
    box_fig.add_trace(go.Box(y=all_moves["before"], name=f"Before move (n={len(all_moves)})", marker_color="steelblue"))
    box_fig.add_trace(go.Box(y=all_moves["after"], name=f"After move (n={len(all_moves)})", marker_color="crimson"))
    box_fig.update_layout(title=f"{label} — before vs. after cross-league moves (all players)", yaxis_title=label)
    st.plotly_chart(box_fig, use_container_width=True)

    verdict1 = "SUPPORTED" if w_pval < 0.05 and median_delta < 0 else (
        "NOT SUPPORTED" if w_pval < 0.05 else "INCONCLUSIVE")
    badge1 = {"SUPPORTED": "🔴", "NOT SUPPORTED": "🟢", "INCONCLUSIVE": "🟡"}[verdict1]

    c1, c2, c3 = st.columns(3)
    c1.metric("p-value", f"{w_pval:.4f}")
    c2.metric("Median change", f"{median_delta:+.3f}")
    c3.metric("Verdict", f"{badge1} {verdict1}")

    st.caption(
        "SUPPORTED means a significant decline after moving leagues (consistent "
        "with an adaptation dip). NOT SUPPORTED means a significant change in "
        "the OPPOSITE direction (players improved). n is small by nature — "
        "genuine cross-league moves are rare events even across 5 leagues x 3 "
        "seasons — so treat this as suggestive rather than definitive."
    )

    with st.expander("All detected moves (raw data)"):
        st.dataframe(all_moves[["player_name", "from_league", "to_league", "before", "after", "delta"]],
                     use_container_width=True, hide_index=True)

# ===========================================================
# SAVE VERDICT
# ===========================================================
verdict_record = {
    "hypothesis": "H1 — League Adaptation (cross-league moves only)",
    "metric": label,
    "test_1": {
        "name": "Wilcoxon Signed-Rank (Before vs. After Cross-League Move, All Players)",
        "n_moves": int(len(all_moves)),
        "p_value": float(w_pval) if w_pval is not None else None,
        "median_delta": float(median_delta) if median_delta is not None else None,
        "verdict": verdict1,
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h1.json", "w") as f:
    json.dump(verdict_record, f, indent=2)