import streamlit as st
import duckdb
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

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
    title=f"{player_name} — {label} by season (red marker = first PL season, per scope note above)",
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

    # -------------------------------
    # Own-season comparison: THIS player's debut season vs. THIS
    # player's own later seasons. Different question from the group
    # comparison above — "did new signings underperform vets league-
    # wide" vs. "did this specific player improve after debut". A
    # within-player (paired) comparison, not a between-player one.
    # -------------------------------
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
            st.metric(
                f"Change from debut to later seasons ({direction})",
                f"{delta:+.2f}",
            )

        st.caption(
            "This is a within-player (paired) comparison — this specific "
            "player's own debut-season number against the average of their "
            "own later seasons. Different from the group chart above, which "
            "compares different players to each other within one season. "
            "The population-level version of this comparison (paired across "
            "every player who has both a debut and later season) uses a "
            "Wilcoxon signed-rank test — more statistically powerful than "
            "the group comparison, since it controls for each player's own "
            "baseline ability rather than comparing unrelated players."
        )

# ===========================================================
# STATISTICAL VERDICT — H1, pooled across ALL players/seasons
# (not just the selected player's context above). This is the
# real test; everything above this point is single-player
# exploration to build intuition first.
# ===========================================================
st.markdown("---")
st.header("H1 Statistical Verdict (All Players, Pooled)")

eligible = player_seasons[player_seasons["minutes"] >= 90].dropna(subset=[col])

# -----------------------------------------------------------
# Test 1: Mann-Whitney U — new players (independent group)
# vs. established players (independent group), pooled across
# every season in the dataset.
# -----------------------------------------------------------
st.subheader("Test 1 — New vs. Established Players (Mann-Whitney U)")

new_group = eligible[eligible["is_new_season"]][col]
established_group = eligible[~eligible["is_new_season"]][col]

if len(new_group) < 5 or len(established_group) < 5:
    st.info("Not enough data in one or both groups to run this test reliably.")
else:
    u_stat, u_pval = stats.mannwhitneyu(new_group, established_group, alternative="two-sided")
    n1, n2 = len(new_group), len(established_group)
    rank_biserial = 1 - (2 * u_stat) / (n1 * n2)  # effect size, -1 to 1

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
        "H1. A negative effect size that isn't significant, or a p-value ≥ 0.05, "
        "means the data doesn't support a real gap."
    )

# -----------------------------------------------------------
# Test 2: Mixed-effects regression — uses EVERY eligible season
# row per player (not collapsed into one "later average"), with
# a random intercept per player to control for each player's
# own baseline ability before estimating the debut-season effect.
# Model: metric ~ is_new_season + (1 | player_id)
# -----------------------------------------------------------
st.subheader("Test 2 — Debut Season Effect (Mixed-Effects Regression)")

import statsmodels.formula.api as smf

# only players with 2+ eligible seasons contribute meaningfully
# to the random-intercept estimate — same requirement the paired
# test had, just checked per-player rather than pre-collapsed
season_counts = eligible.groupby("player_id")["season"].transform("count")
model_data = eligible[season_counts >= 2].copy()
model_data["is_new_season_int"] = model_data["is_new_season"].astype(int)

if model_data["player_id"].nunique() < 10:
    st.info("Not enough players with 2+ eligible seasons to fit this model reliably.")
else:
    mixed_model = smf.mixedlm(
        f"{col} ~ is_new_season_int",
        data=model_data,
        groups=model_data["player_id"],
    ).fit()

    debut_coef = mixed_model.params["is_new_season_int"]
    debut_pval = mixed_model.pvalues["is_new_season_int"]
    ci_low, ci_high = mixed_model.conf_int().loc["is_new_season_int"]

    # forest plot: single estimate + 95% CI whiskers
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

    # per-player trajectories: real season on x-axis, debut point
    # marked distinctly, selected player highlighted
    sample_ids = model_data["player_id"].drop_duplicates().sample(
        min(40, model_data["player_id"].nunique()), random_state=0
    )
    if player_id not in sample_ids.values:
        sample_ids = pd.concat([sample_ids, pd.Series([player_id])])

    traj_fig = go.Figure()
    for pid in sample_ids:
        p_rows = model_data[model_data["player_id"] == pid].sort_values("season")
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
        f"({len(model_data)} player-season rows total). The coefficient is the "
        f"model's estimate of how much lower (if negative) a player's {label} is "
        f"in their debut season specifically, after accounting for each player's "
        f"own baseline ability via the random intercept. A negative, significant "
        f"coefficient supports H1. Note: with only 3 seasons of data, most "
        f"players contribute at most 1-2 'later' seasons to their own baseline "
        f"estimate — a real limitation on how precisely individual baselines "
        f"are known, worth stating in any write-up of this result."
    )

# ===========================================================
# SAVE VERDICT — so the Myth Verdict page can read this
# result without recomputing it. Guards against either test
# having been skipped (insufficient data) above.
# ===========================================================
import json
from datetime import datetime, timezone

verdict_record = {
    "hypothesis": "H1 — League Adaptation",
    "metric": label,
    "test_1": {
        "name": "Mann-Whitney U (New vs. Established Players)",
        "p_value": float(u_pval) if "u_pval" in dir() else None,
        "effect_size": float(rank_biserial) if "rank_biserial" in dir() else None,
        "verdict": verdict1 if "verdict1" in dir() else "NOT COMPUTED",
    },
    "test_2": {
        "name": "Mixed-Effects Regression (Debut vs. Own Later Seasons)",
        "p_value": float(debut_pval) if "debut_pval" in dir() else None,
        "coefficient": float(debut_coef) if "debut_coef" in dir() else None,
        "verdict": verdict2 if "verdict2" in dir() else "NOT COMPUTED",
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h1.json", "w") as f:
    json.dump(verdict_record, f, indent=2)