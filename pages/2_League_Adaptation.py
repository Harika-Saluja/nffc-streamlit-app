import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
import statsmodels.formula.api as smf
import json
from datetime import datetime, timezone

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="League Adaptation", layout="wide")
st.title("League Adaptation")
st.caption(
    "H1: Players new to the league show a measurable dip in performance "
    "in their first season compared to established players."
)

st.warning(
    "**Scope note:** with the multi-league rebuild, this dataset now covers "
    "all 5 top European leagues (Premier League, La Liga, Serie A, "
    "1. Bundesliga, Ligue 1), so 'new' here can reflect a genuine cross-"
    "league transfer. A player's first tracked season (2022-23) is still "
    "excluded from the 'new' flag, since we can't tell whether they're a "
    "genuine debutant or simply outside our data window (left-censoring)."
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
            m.season, m.match_date, m.competition,
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

player_seasons["xg_90"] = player_seasons.apply(
    lambda r: (r["xg_total"] / r["minutes"] * 90) if r["minutes"] > 0 else None, axis=1
)
player_seasons["events_90"] = player_seasons.apply(
    lambda r: (r["events_total"] / r["minutes"] * 90) if r["minutes"] > 0 else None, axis=1
)

first_season = player_seasons.groupby("player_id")["season"].min().rename("first_season")
player_seasons = player_seasons.merge(first_season, on="player_id")

EARLIEST_DATASET_SEASON = player_seasons["season"].min()
player_seasons["is_new_season"] = (
    (player_seasons["season"] == player_seasons["first_season"])
    & (player_seasons["first_season"] != EARLIEST_DATASET_SEASON)
)

# -------------------------------
# Sidebar – full player roster
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
# Per-season trend, first/new season highlighted (LINE CHART)
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

fig = go.Figure(go.Scatter(
    x=player_data["season"], y=player_data[col],
    mode="lines+markers",
    line=dict(color="steelblue", width=2),
    marker=dict(size=14, color=colors, line=dict(width=1, color="white")),
    text=[f"{v:.2f}" if pd.notna(v) else "—" for v in player_data[col]],
    textposition="top center",
    texttemplate="%{text}",
))
fig.update_layout(
    title=f"{player_name} — {label} by season (red marker = first season, per scope note above)",
    xaxis_title="Season", yaxis_title=label,
)
st.plotly_chart(fig, use_container_width=True)

if not player_data["is_new_season"].any():
    if player_data["first_season"].iloc[0] == EARLIEST_DATASET_SEASON:
        st.info(
            f"{player_name}'s first tracked season is {EARLIEST_DATASET_SEASON} — "
            f"the earliest season in our dataset, so we can't confirm this is "
            f"genuinely their first season (left-censored)."
        )
    else:
        st.info(f"{player_name} has no flagged 'new' season in this window.")

# -------------------------------
# Population comparison: new-season players vs. established players
# -------------------------------
new_rows = player_data[player_data["is_new_season"]]

if not new_rows.empty:
    st.markdown("---")
    st.subheader("Context: New vs. Established Players That Season")

    target_season = new_rows["season"].iloc[0]
    cohort = player_seasons[
        (player_seasons["season"] == target_season) & (player_seasons["minutes"] >= 90)
    ]

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
        f"single-season snapshot, not the full statistical test — see below "
        f"for the pooled, population-level verdict."
    )

    later_seasons = player_data[player_data["season"] > target_season]

    if later_seasons.empty:
        st.info(
            f"{player_name} has no seasons after their debut ({target_season}) "
            f"in the dataset yet, so an own-season comparison isn't possible."
        )
    else:
        st.markdown("---")
        st.subheader(f"{player_name}'s Own Debut Season vs. Later Seasons")

        debut_value = new_rows[col].iloc[0]
        later_avg = later_seasons[col].mean()
        delta = later_avg - debut_value if pd.notna(later_avg) and pd.notna(debut_value) else None

        own_fig = go.Figure(go.Bar(
            x=[f"Debut season ({target_season})", "Average of later seasons"],
            y=[debut_value, later_avg],
            marker_color=["crimson", "seagreen"],
            text=[f"{v:.2f}" if pd.notna(v) else "—" for v in [debut_value, later_avg]],
            textposition="outside",
        ))
        own_fig.update_layout(
            title=f"{player_name} — {label}: debut season vs. own later average",
            yaxis_title=label,
        )
        st.plotly_chart(own_fig, use_container_width=True)

        if delta is not None:
            direction = "improved" if delta > 0 else "declined"
            st.metric(f"Change from debut to later seasons ({direction})", f"{delta:+.2f}")

        st.caption(
            "This is a within-player (paired) comparison — this specific "
            "player's own debut-season number against the average of their "
            "own later seasons. The population-level version uses mixed-"
            "effects regression, shown below."
        )

# ===========================================================
# STATISTICAL VERDICT — H1, pooled across ALL players/seasons
# ===========================================================
st.markdown("---")
st.header("H1 Statistical Verdict (All Players, Pooled)")

eligible = player_seasons[player_seasons["minutes"] >= 90].dropna(subset=[col])

# -----------------------------------------------------------
# Test 1: Mann-Whitney U — new players vs. established players
# -----------------------------------------------------------
st.subheader("Test 1 — New vs. Established Players (Mann-Whitney U)")

new_group = eligible[eligible["is_new_season"]][col]
established_group = eligible[~eligible["is_new_season"]][col]

verdict1 = "NOT COMPUTED"
u_pval = None
rank_biserial = None

if len(new_group) < 5 or len(established_group) < 5:
    st.info("Not enough data in one or both groups to run this test reliably.")
else:
    u_stat, u_pval = stats.mannwhitneyu(new_group, established_group, alternative="two-sided")
    n1, n2 = len(new_group), len(established_group)
    rank_biserial = 1 - (2 * u_stat) / (n1 * n2)

    box_fig = go.Figure()
    box_fig.add_trace(go.Box(y=new_group, name=f"New (n={n1})", marker_color="crimson"))
    box_fig.add_trace(go.Box(y=established_group, name=f"Established (n={n2})", marker_color="steelblue"))
    box_fig.update_layout(title=f"{label} distribution — new vs. established players", yaxis_title=label)
    st.plotly_chart(box_fig, use_container_width=True)

    verdict1 = "SUPPORTED" if u_pval < 0.05 and rank_biserial < 0 else (
        "NOT SUPPORTED" if u_pval < 0.05 else "INCONCLUSIVE")
    badge_color1 = {"SUPPORTED": "🔴", "NOT SUPPORTED": "🟢", "INCONCLUSIVE": "🟡"}[verdict1]

    c1, c2, c3 = st.columns(3)
    c1.metric("p-value", f"{u_pval:.4f}")
    c2.metric("Effect size (rank-biserial)", f"{rank_biserial:+.3f}")
    c3.metric("Verdict", f"{badge_color1} {verdict1}")

    st.caption(
        "p < 0.05 and a negative effect size means new players' distribution "
        "sits significantly lower than established players' — consistent with "
        "H1. Note: with a large sample, statistical significance doesn't "
        "guarantee practical significance — check the effect size magnitude too."
    )

# -----------------------------------------------------------
# Test 2: Mixed-effects regression — debut season effect,
# controlling for each player's own baseline via random intercept
# -----------------------------------------------------------
st.subheader("Test 2 — Debut Season Effect (Mixed-Effects Regression)")

season_counts = eligible.groupby("player_id")["season"].transform("count")
model_data = eligible[season_counts >= 2].copy()
model_data["is_new_season_int"] = model_data["is_new_season"].astype(int)

verdict2 = "NOT COMPUTED"
debut_pval = None
debut_coef = None

# BUGFIX: the original code only checked that there were >=10 players
# in model_data, but never checked that `is_new_season_int` actually
# varies within that filtered subset. Players who qualify for this
# model need 2+ eligible seasons — and it's entirely possible (and, in
# some season windows, likely) that none of the "new" flagged rows
# survive that filter, leaving is_new_season_int constant at 0 for
# every row. A constant predictor gives mixedlm a singular design
# matrix, which raises an unhandled numpy.linalg.LinAlgError and
# crashes the whole page. FIX: require both classes to be present
# with a minimum count, and wrap the fit itself in try/except so a
# convergence failure degrades to a message instead of a crash.
class_counts = model_data["is_new_season_int"].value_counts()
has_both_classes = len(class_counts) == 2 and class_counts.min() >= 5

if model_data["player_id"].nunique() < 10:
    st.info("Not enough players with 2+ eligible seasons to fit this model reliably.")
elif not has_both_classes:
    st.info(
        "Not enough players flagged as 'new' (with 2+ eligible seasons) in this "
        "window to estimate a debut-season effect — the model needs both debut "
        "and established rows to compare."
    )
else:
    mixed_model = None
    try:
        mixed_model = smf.mixedlm(
            f"{col} ~ is_new_season_int", data=model_data, groups=model_data["player_id"]
        ).fit()
    except Exception as e:
        st.info(f"The mixed-effects model failed to converge on this data slice ({e}).")

    if mixed_model is not None:
        debut_coef = mixed_model.params["is_new_season_int"]
        debut_pval = mixed_model.pvalues["is_new_season_int"]
        ci_low, ci_high = mixed_model.conf_int().loc["is_new_season_int"]

        forest_fig = go.Figure()
        forest_fig.add_trace(go.Scatter(
            x=[debut_coef], y=["Debut season effect"],
            error_x=dict(type="data", symmetric=False,
                         array=[ci_high - debut_coef], arrayminus=[debut_coef - ci_low]),
            mode="markers", marker=dict(size=14, color="crimson"),
        ))
        forest_fig.add_vline(x=0, line_dash="dash", line_color="gray")
        forest_fig.update_layout(
            title=f"Estimated debut-season effect on {label} (95% CI)",
            xaxis_title=f"Change in {label} vs. established seasons",
        )
        st.plotly_chart(forest_fig, use_container_width=True)

        sample_ids = model_data["player_id"].drop_duplicates().sample(
            min(40, model_data["player_id"].nunique()), random_state=0
        )
        # only force-add the selected player if they actually qualify for this
        # model (2+ eligible seasons) — forcing in a player with zero rows in
        # model_data causes an IndexError below when the chart tries to read
        # their name from an empty dataframe
        if player_id in model_data["player_id"].values and player_id not in sample_ids.values:
            sample_ids = pd.concat([sample_ids, pd.Series([player_id])])

        if player_id not in model_data["player_id"].values:
            st.info(
                f"{player_name} doesn't have 2+ eligible seasons, so they aren't "
                f"part of this pooled model and won't appear (highlighted) in "
                f"the trajectory chart below — it still shows the population."
            )

        traj_fig = go.Figure()
        for pid in sample_ids:
            p_rows = model_data[model_data["player_id"] == pid].sort_values("season")
            if p_rows.empty:  # defensive: skip rather than crash on .iloc[0]
                continue
            is_selected = pid == player_id
            traj_fig.add_trace(go.Scatter(
                x=p_rows["season"], y=p_rows[col],
                mode="lines+markers",
                line=dict(color="gold" if is_selected else "gray", width=3 if is_selected else 1),
                opacity=1.0 if is_selected else 0.3,
                marker=dict(
                    size=[12 if new else 7 for new in p_rows["is_new_season"]],
                    symbol=["star" if new else "circle" for new in p_rows["is_new_season"]],
                ),
                name=p_rows["player_name"].iloc[0] if is_selected else "",
                showlegend=is_selected,
                hovertext=p_rows["player_name"].iloc[0],
            ))
        traj_fig.update_layout(
            title=f"{label} by season, per player (★ = that player's debut season)",
            xaxis_title="Season", yaxis_title=label, showlegend=True,
        )
        st.plotly_chart(traj_fig, use_container_width=True)

        verdict2 = "SUPPORTED" if debut_pval < 0.05 and debut_coef < 0 else (
            "NOT SUPPORTED" if debut_pval < 0.05 else "INCONCLUSIVE")
        badge_color2 = {"SUPPORTED": "🔴", "NOT SUPPORTED": "🟢", "INCONCLUSIVE": "🟡"}[verdict2]

        c1, c2, c3 = st.columns(3)
        c1.metric("Coefficient (debut effect)", f"{debut_coef:+.3f}")
        c2.metric("p-value", f"{debut_pval:.4f}")
        c3.metric("Verdict", f"{badge_color2} {verdict2}")

        st.caption(
            f"n={model_data['player_id'].nunique()} players with 2+ eligible seasons "
            f"({len(model_data)} player-season rows total). Negative, significant "
            f"coefficient supports H1. With only 3 seasons of data, most players "
            f"contribute at most 1-2 'later' seasons to their own baseline estimate."
        )

# ===========================================================
# SAVE VERDICT
# ===========================================================
verdict_record = {
    "hypothesis": "H1 — League Adaptation",
    "metric": label,
    "test_1": {
        "name": "Mann-Whitney U (New vs. Established Players)",
        "p_value": float(u_pval) if u_pval is not None else None,
        "effect_size": float(rank_biserial) if rank_biserial is not None else None,
        "verdict": verdict1,
    },
    "test_2": {
        "name": "Mixed-Effects Regression (Debut vs. Own Later Seasons)",
        "p_value": float(debut_pval) if debut_pval is not None else None,
        "coefficient": float(debut_coef) if debut_coef is not None else None,
        "verdict": verdict2,
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h1.json", "w") as f:
    json.dump(verdict_record, f, indent=2)

# ===========================================================
# TRANSFER CONTEXT — lightweight exploratory extension, NOT a
# replication of Dinsdale & Gallagher (2022) "Transfer Portal" or
# Hong et al. (2025/26) "EventGPT". Those papers need infrastructure
# this project doesn't have (a global Elo-style league/team rating
# system trained on years of results, actual transfer-date records,
# or raw sequential event data with coordinates for a trained
# transformer's player embeddings). This section borrows their
# FOUR-FACTOR FRAMING and the IDEA of vector-based player similarity,
# built from data already available here — proxies, not replicas.
#
#   Paper's factor              -> Our proxy
#   Playing style difference    -> per-90 (xG, pass%, events) as a
#                                   simple 3-value "style vector",
#                                   compared via cosine similarity
#   Teammate/team ability       -> team points-per-game that season
#   League quality/style        -> league-wide average per-90 output
#                                   that season (NOT a true Elo rating)
#   Desired role                -> primary_position match/mismatch
# ===========================================================
st.markdown("---")
st.header("Transfer Context (Lightweight Extension)")
st.warning(
    "**This is a lightweight, differently-scoped extension** inspired by "
    "the four-factor framing in Dinsdale & Gallagher (2022) 'Transfer "
    "Portal' and the player-embedding idea in Hong et al. (2025/26) "
    "'EventGPT' — not a replication of either. Both papers require "
    "infrastructure (a global Elo-style rating system, real transfer "
    "dates, or raw sequential event data for a trained transformer) "
    "that doesn't exist in this project's data. The 'league quality' "
    "score below is a rough per-90 output proxy, NOT a validated "
    "strength rating like Transfer Portal's Elo system — treat it as "
    "illustrative, not authoritative."
)

# --- detect a REAL cross-league move for the selected player ---
# BUGFIX: the original version compared the *full set* of distinct
# competitions a player appeared in each season. Any player who also
# featured in a continental cup (e.g. UEFA Champions League) — or who
# simply has a season with no domestic-league appearances recorded —
# ends up with a competition set that doesn't overlap with the
# adjacent season's, which the old code mistook for a "cross-league
# move" even though the player never left their domestic league.
# It also picked `list(some_set)[0]`, which is non-deterministic
# (Python set/string-hash ordering isn't guaranteed) whenever a season
# genuinely had more than one competition.
# FIX: reduce each season down to a single "primary league" — the
# competition with the most matches played that season — and compare
# primary leagues season-to-season instead of raw competition sets.
player_leagues = con.execute(f"""
    SELECT m.season, m.competition, COUNT(DISTINCT l.match_id) AS matches_played
    FROM lineups l JOIN matches m ON l.match_id = m.match_id
    WHERE l.player_id = {player_id}
    GROUP BY m.season, m.competition
    ORDER BY m.season
""").df()

# Taking the highest-match-count competition per season still misfires
# if a season has ONLY cup/continental matches recorded (no domestic
# league appearances at all that season, e.g. a data gap or a loan to
# a reserve/cup side) — the cup competition would then "win" as the
# only option. Exclude clearly non-domestic-league competitions by
# name before picking a primary league; a season with nothing left
# afterwards is treated as no usable data, not a false switch.
_non_domestic_pattern = r"(?i)cup|champions league|europa|conference league|play-?off|super cup|shield"
domestic_leagues = player_leagues[
    ~player_leagues["competition"].str.contains(_non_domestic_pattern, regex=True, na=False)
]

league_switch = None
if len(domestic_leagues) >= 2 and domestic_leagues["season"].nunique() >= 2:
    primary_league_by_season = (
        domestic_leagues.sort_values("matches_played", ascending=False)
        .drop_duplicates(subset=["season"], keep="first")
        .set_index("season")["competition"]
    )
    seasons_sorted = sorted(primary_league_by_season.index)
    for i in range(1, len(seasons_sorted)):
        prev_league = primary_league_by_season[seasons_sorted[i - 1]]
        curr_league = primary_league_by_season[seasons_sorted[i]]
        if prev_league != curr_league:
            league_switch = {
                "from_league": prev_league,
                "to_league": curr_league,
                "from_season": seasons_sorted[i-1],
                "to_season": seasons_sorted[i],
            }
            break

if league_switch is None:
    st.info(
        f"No detected cross-league move for {player_name} in this dataset "
        f"— either they stayed in one league throughout, or their move "
        f"happened outside the tracked seasons."
    )
else:
    st.success(
        f"**Detected move:** {league_switch['from_league']} "
        f"({league_switch['from_season']}) → {league_switch['to_league']} "
        f"({league_switch['to_season']})"
    )

    # --- performance change: last season in old league vs first in new ---
    before = player_seasons[
        (player_seasons["player_id"] == player_id)
        & (player_seasons["season"] == league_switch["from_season"])
    ]
    after = player_seasons[
        (player_seasons["player_id"] == player_id)
        & (player_seasons["season"] == league_switch["to_season"])
    ]

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

    # --- four-factor breakdown ---
    st.subheader("Four-Factor Breakdown")

    # 1. Style similarity: cosine sim of (xg_90, pass_success_avg, events_90)
    #    before vs. the new league's average that season
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

    # 2. Team ability: points-per-game, old team vs new team
    def team_ppg(player_id_, season_):
        team_matches = con.execute(f"""
            SELECT m.home_team, m.away_team, m.home_score, m.away_score, l.team_name
            FROM lineups l JOIN matches m ON l.match_id = m.match_id
            WHERE l.player_id = {player_id_} AND m.season = '{season_}'
        """).df()
        if team_matches.empty:
            return None
        points = []
        for _, row in team_matches.iterrows():
            if row["team_name"] == row["home_team"]:
                gf, ga = row["home_score"], row["away_score"]
            else:
                gf, ga = row["away_score"], row["home_score"]
            points.append(3 if gf > ga else (1 if gf == ga else 0))
        return np.mean(points) if points else None

    old_team_ppg = team_ppg(player_id, league_switch["from_season"])
    new_team_ppg = team_ppg(player_id, league_switch["to_season"])

    # 3. League quality proxy: league-wide average per-90 output that season
    def league_quality(competition_, season_):
        q = player_seasons[
            (player_seasons["season"] == season_)
        ]
        # filter to players who appeared in that competition that season
        comp_players = con.execute(f"""
            SELECT DISTINCT l.player_id
            FROM lineups l JOIN matches m ON l.match_id = m.match_id
            WHERE m.competition = '{competition_}' AND m.season = '{season_}'
        """).df()["player_id"]
        q = q[q["player_id"].isin(comp_players)]
        return q[col].mean() if not q.empty else None

    old_league_quality = league_quality(league_switch["from_league"], league_switch["from_season"])
    new_league_quality = league_quality(league_switch["to_league"], league_switch["to_season"])

    # 4. Role/position consistency
    old_position = con.execute(f"""
        SELECT primary_position, COUNT(*) AS n FROM lineups l
        JOIN matches m ON l.match_id = m.match_id
        WHERE l.player_id = {player_id} AND m.season = '{league_switch['from_season']}'
        GROUP BY primary_position ORDER BY n DESC LIMIT 1
    """).df()
    new_position = con.execute(f"""
        SELECT primary_position, COUNT(*) AS n FROM lineups l
        JOIN matches m ON l.match_id = m.match_id
        WHERE l.player_id = {player_id} AND m.season = '{league_switch['to_season']}'
        GROUP BY primary_position ORDER BY n DESC LIMIT 1
    """).df()
    old_pos_val = old_position["primary_position"].iloc[0] if not old_position.empty else None
    new_pos_val = new_position["primary_position"].iloc[0] if not new_position.empty else None
    same_position = old_pos_val == new_pos_val if old_pos_val and new_pos_val else None

    # BUGFIX: `.mean()` on an all-NaN slice (e.g. a season with no
    # recorded events data for a given metric) returns NaN, not None.
    # The original `is not None` checks let NaN through, so the metric
    # rendered the literal string "nan" instead of the intended "—"
    # placeholder. Use pd.notna(), which treats NaN as missing too.
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "1. Style similarity",
        f"{style_similarity:.2f}" if pd.notna(style_similarity) else "—",
        help="Cosine similarity (0-1) between the player's own style vector "
             "and the new league's average — higher means a more natural stylistic fit.",
    )
    c2.metric(
        "2. Team ability (PPG)",
        f"{old_team_ppg:.2f} → {new_team_ppg:.2f}" if pd.notna(old_team_ppg) and pd.notna(new_team_ppg) else "—",
        help="Points-per-game of old team vs. new team that season.",
    )
    c3.metric(
        "3. League quality (proxy)",
        f"{old_league_quality:.2f} → {new_league_quality:.2f}" if pd.notna(old_league_quality) and pd.notna(new_league_quality) else "—",
        help=f"League-wide average {label} — a rough proxy, not a validated strength rating.",
    )
    c4.metric(
        "4. Same role?",
        "Yes" if same_position else ("No" if same_position is not None else "—"),
        help=f"{old_pos_val or '—'} → {new_pos_val or '—'}",
    )

    # --- recommended replacements: style-vector similarity within the
    # OLD league/position, to suggest who could fill the departing
    # player's role — borrows EventGPT's embedding-similarity IDEA,
    # not its architecture (no transformer, no learned embeddings —
    # just cosine similarity on the same 3-value per-90 style vector) ---
    st.subheader(f"Suggested Replacements in {league_switch['from_league']}")

    if old_pos_val is not None and player_style is not None:
        candidates = con.execute(f"""
            SELECT DISTINCT l.player_id, l.player_name
            FROM lineups l JOIN matches m ON l.match_id = m.match_id
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
            sim = float(
                np.dot(player_style, cand_style)
                / (np.linalg.norm(player_style) * np.linalg.norm(cand_style))
            )
            sims.append({"Player": cand["player_name"], "Style Similarity": round(sim, 3)})

        if sims:
            sims_df = pd.DataFrame(sims).sort_values("Style Similarity", ascending=False).head(5)
            st.dataframe(sims_df, use_container_width=True, hide_index=True)
            st.caption(
                f"Top 5 players in the {old_pos_val} position, {league_switch['from_league']} "
                f"{league_switch['from_season']}, ranked by style-vector similarity to "
                f"{player_name} before their move. This is a simple cosine-similarity "
                f"ranking on 3 per-90 stats — not a trained model — so treat it as a "
                f"starting point for scouting, not a definitive recommendation."
            )
        else:
            st.info("No comparable players found for a replacement suggestion.")
    else:
        st.info("Not enough data to suggest replacements for this player/season.")