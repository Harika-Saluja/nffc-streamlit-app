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
st.set_page_config(page_title="Myth Verdict", layout="wide")
st.title("MYTH VERDICT")
st.caption(
    "A summary scorecard across all four tested hypotheses, plus an "
    "early recommendation tool that combines them into a single "
    "league-fit score per player."
)

# ===========================================================
# PART 1 — HYPOTHESIS SCORECARD
#
# Reads verdict_h1.json..verdict_h4.json, written independently by the
# League Adaptation, Workload & Injury Risk, Age Optimization, and
# Squad Optimizer pages. IMPORTANT: these are NOT all the same kind of
# result — H1 is a per-player-move snapshot, H2/H4 are pooled
# statistical tests, H3's headline numbers have a known methodology
# concern (see its own caveat below). This scorecard displays them
# side by side for convenience; it does not average or combine their
# verdicts into one number, because they are not comparable that way.
# ===========================================================
st.header("Hypothesis Scorecard")


def load_verdict(filename: str):
    if not os.path.exists(filename):
        return None
    try:
        with open(filename) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def normalize_h1(v):
    if v is None:
        return None
    verdict_text = v.get("performance_change_verdict") or "Not computed"
    badge = {
        "Positive across all metrics": "🟢",
        "Negative across all metrics": "🔴",
    }.get(verdict_text, "🟡")
    move = v.get("move", {})
    key_stat = (
        f"{v.get('player_name', '—')}: {move.get('from_league', '?')} "
        f"({move.get('from_season', '?')}) → {move.get('to_league', '?')} "
        f"({move.get('to_season', '?')})"
    )
    return {
        "id": "H1", "name": "League Adaptation", "badge": badge,
        "verdict_text": verdict_text, "key_stat": key_stat,
        "caveat": (
            "Per-player snapshot — reflects only the last player viewed "
            "on that page, NOT a pooled test across every player like "
            "H2/H3/H4. Refresh by visiting League Adaptation with a "
            "different player selected."
        ),
    }


def normalize_h2(v):
    if v is None:
        return None
    t1, t2 = v.get("test_1", {}), v.get("test_2", {})
    verdicts = [t1.get("verdict"), t2.get("verdict")]
    if "SUPPORTED" in verdicts:
        badge, text = "🟡", "Partially supported"
    elif verdicts and all(x == "NOT SUPPORTED" for x in verdicts if x):
        badge, text = "🟢", "Not supported"
    elif verdicts and all(x is None for x in verdicts):
        badge, text = "⚪", "Not computed"
    else:
        badge, text = "🟡", "Inconclusive"
    sig = t2.get("significant_predictors", [])
    key_stat = f"Significant load metric(s): {', '.join(sig) if sig else 'none'}"
    return {
        "id": "H2", "name": "Workload & Injury Risk", "badge": badge,
        "verdict_text": text, "key_stat": key_stat,
        "caveat": (
            "Test 1 (Mann-Whitney) and Test 2 (logistic regression) can "
            "disagree — only Test 2 found a significant metric (a_sum) "
            "in the reference run. The separate ACWR U-shape test "
            "(Test 3) isn't captured in this JSON — check that page "
            "directly, since its shape didn't match the U-shaped "
            "hypothesis in the one run reviewed."
        ),
    }


def normalize_h3(v):
    if v is None:
        return None
    domains = v.get("method_b", {}).get("domains", {})
    peaks = ", ".join(
        f"{k}: {d.get('peak_age'):.1f}y" for k, d in domains.items()
        if d.get("peak_age") is not None
    )
    return {
        "id": "H3", "name": "Age Optimization", "badge": "⚠️",
        "verdict_text": "Methodology flagged — pending review",
        "key_stat": peaks or "No domain data available",
        "caveat": (
            "The clustering behind these peak-age and effect-size "
            "numbers splits sessions by z-score, then tests that SAME "
            "z-score for group differences — a structurally circular "
            "setup that can produce large, 'significant'-looking effect "
            "sizes regardless of any real age relationship. The page's "
            "own mixed-effects model (age_bucket + position) is a more "
            "trustworthy source for this hypothesis, but isn't saved "
            "to this JSON yet."
        ),
    }


def normalize_h4(v):
    if v is None:
        return None
    tl, il = v.get("team_level", {}), v.get("individual_level", {})
    tl_verdict, il_verdict = tl.get("verdict"), il.get("verdict")
    parts = []
    if tl_verdict:
        parts.append(f"Team-level: {tl_verdict.title()}")
    if il_verdict:
        parts.append(f"Individual-level: {il_verdict.title()}")
    text = " · ".join(parts) if parts else "Not computed"
    if tl_verdict == "SIGNIFICANT RELATIONSHIP" or il_verdict == "SIGNIFICANT INTERACTION FOUND":
        badge = "🟡"
    elif tl_verdict or il_verdict:
        badge = "🟢"
    else:
        badge = "⚪"
    rho = tl.get("spearman_rho")
    key_stat = f"Diversity–PPG ρ = {rho:+.3f}" if rho is not None else "—"
    caveat_parts = []
    if rho is not None and rho > 0:
        caveat_parts.append(
            "Team-level relationship is POSITIVE — the opposite "
            "direction from Maderer et al. (2014)'s original finding."
        )
    if il.get("foreign_age_interaction_p", 1) is not None and il.get("foreign_age_interaction_p", 1) > 0.05:
        caveat_parts.append(
            "Individual-level foreign×age and foreign×signings "
            "interactions did not replicate Lago et al. (2023)."
        )
    return {
        "id": "H4", "name": "Squad Optimizer", "badge": badge,
        "verdict_text": text, "key_stat": key_stat,
        "caveat": " ".join(caveat_parts) if caveat_parts else None,
    }


hypotheses = [
    normalize_h1(load_verdict("verdict_h1.json")),
    normalize_h2(load_verdict("verdict_h2.json")),
    normalize_h3(load_verdict("verdict_h3.json")),
    normalize_h4(load_verdict("verdict_h4.json")),
]

cols = st.columns(4)
for col, h in zip(cols, hypotheses):
    with col:
        if h is None:
            st.markdown("**— Not computed —**")
            st.caption("Visit that page at least once to generate its verdict file.")
            continue
        st.markdown(f"### {h['badge']} {h['id']}")
        st.markdown(f"**{h['name']}**")
        st.markdown(h["verdict_text"])
        st.caption(h["key_stat"])
        if h.get("caveat"):
            with st.expander("Caveat"):
                st.caption(h["caveat"])

st.caption(
    "Badges are shown per hypothesis independently — they are not "
    "averaged or combined into one score, since each hypothesis uses a "
    "different test, outcome variable, and (for H1) scope."
)

# ===========================================================
# PART 2 — LEAGUE FIT RECOMMENDATION (early version)
#
# Combines Factor 1 (style similarity) and Factor 3 (league quality
# proxy) from League Adaptation, plus a league-wide team-ability proxy,
# into one transparent, equally-weighted fit score per candidate
# destination league. This is NOT the standardized-coefficient version
# discussed as the long-term goal (that needs the combined regression
# across H1/H2/H3/H4 to be built first) — weights here are equal by
# construction, shown openly, and meant to be replaced once that
# regression exists.
# ===========================================================
st.markdown("---")
st.header("League Fit Recommendation (Early Version)")
st.warning(
    "**Early version — equal weights, not yet model-derived.** This "
    "combines the same lightweight proxies from League Adaptation "
    "(style similarity, league quality) with a team-ability proxy, "
    "using min-max normalization and equal weighting across candidate "
    "leagues. It does not yet fold in H2 (injury risk), H3 (age "
    "readiness), or H4 (squad fit) — see the roadmap note at the "
    "bottom of this section."
)

con = duckdb.connect(database=':memory:')
con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events  AS SELECT * FROM read_parquet('events.parquet');
""")

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

player_seasons["xg_90"] = np.where(
    player_seasons["minutes"] > 0,
    player_seasons["xg_total"] / player_seasons["minutes"] * 90, np.nan,
)
player_seasons["events_90"] = np.where(
    player_seasons["minutes"] > 0,
    player_seasons["events_total"] / player_seasons["minutes"] * 90, np.nan,
)
STYLE_COLS = ["xg_90", "pass_success_avg", "events_90"]

players_roster = player_seasons[["player_id", "player_name"]].drop_duplicates().sort_values("player_name")
rec_player_name = st.selectbox("Player to evaluate:", players_roster["player_name"], key="rec_player")
rec_player_id = int(players_roster.loc[players_roster["player_name"] == rec_player_name, "player_id"].iloc[0])


def team_ppg_league_avg(competition: str, season: str, _con) -> float | None:
    """Average points-per-game across every team that played in this
    competition/season — a league-wide team-strength proxy (there's no
    single destination team in the ranked-shortlist mode, so this
    stands in for Factor 2's team-specific PPG)."""
    teams = _con.execute(f"""
        SELECT DISTINCT team_name FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE m.competition = '{competition}' AND m.season = '{season}'
    """).df()["team_name"]
    if teams.empty:
        return None
    ppgs = []
    for team in teams:
        m = _con.execute(f"""
            SELECT home_team, away_team, home_score, away_score
            FROM matches WHERE season = '{season}'
              AND (home_team = '{team}' OR away_team = '{team}')
        """).df()
        if m.empty:
            continue
        pts = []
        for _, r in m.iterrows():
            if r["home_team"] == team:
                gf, ga = r["home_score"], r["away_score"]
            else:
                gf, ga = r["away_score"], r["home_score"]
            pts.append(3 if gf > ga else (1 if gf == ga else 0))
        if pts:
            ppgs.append(np.mean(pts))
    return float(np.mean(ppgs)) if ppgs else None


def compute_league_fit_scores(player_id: int, player_seasons: pd.DataFrame, _con) -> pd.DataFrame:
    """For the given player's most recent tracked season, score every
    OTHER league present in the dataset (same season, if available —
    else that league's most recent tracked season) on:
      - style similarity (Factor 1's cosine-similarity logic)
      - league quality proxy (Factor 3's xG/90 league average)
      - league-wide average team PPG (team-ability proxy)
    Each component is min-max normalized across the candidate leagues
    (so they're all 0-1 before combining) and averaged with EQUAL
    weight into a 0-100 fit score. Returns a dataframe sorted best-fit
    first, with each raw component included for transparency.
    """
    p_data = player_seasons[player_seasons["player_id"] == player_id].sort_values("season")
    if p_data.empty:
        return pd.DataFrame()

    current_row = p_data.iloc[-1]
    current_league = current_row["competition"]
    player_style = current_row[STYLE_COLS].fillna(0).values.astype(float)
    if np.linalg.norm(player_style) == 0:
        return pd.DataFrame()

    all_leagues = player_seasons["competition"].dropna().unique()
    candidates = []
    for lg in all_leagues:
        if lg == current_league:
            continue
        lg_seasons = player_seasons[player_seasons["competition"] == lg]["season"]
        if lg_seasons.empty:
            continue
        cand_season = sorted(lg_seasons.unique())[-1]  # most recent tracked season for that league

        lg_avg_style = (
            player_seasons[(player_seasons["competition"] == lg) & (player_seasons["season"] == cand_season)]
            [STYLE_COLS].mean().fillna(0).values.astype(float)
        )
        style_sim = None
        if np.linalg.norm(lg_avg_style) > 0:
            style_sim = float(
                np.dot(player_style, lg_avg_style) / (np.linalg.norm(player_style) * np.linalg.norm(lg_avg_style))
            )

        lg_quality_rows = player_seasons[(player_seasons["competition"] == lg) & (player_seasons["season"] == cand_season)]
        lg_quality = float(lg_quality_rows["xg_90"].mean()) if not lg_quality_rows.empty else None

        avg_ppg = team_ppg_league_avg(lg, cand_season, _con)

        candidates.append({
            "League": lg, "Season": cand_season,
            "Style Similarity": style_sim,
            "League Quality (xG/90 avg)": lg_quality,
            "Avg Team PPG": avg_ppg,
        })

    if not candidates:
        return pd.DataFrame()

    cand_df = pd.DataFrame(candidates)

    def min_max(series: pd.Series) -> pd.Series:
        s = series.dropna()
        if s.empty or s.max() == s.min():
            return series.apply(lambda x: 0.5 if pd.notna(x) else np.nan)
        return (series - s.min()) / (s.max() - s.min())

    cand_df["_style_n"] = min_max(cand_df["Style Similarity"])
    cand_df["_quality_n"] = min_max(cand_df["League Quality (xG/90 avg)"])
    cand_df["_ppg_n"] = min_max(cand_df["Avg Team PPG"])

    component_cols = ["_style_n", "_quality_n", "_ppg_n"]
    cand_df["Fit Score"] = cand_df[component_cols].mean(axis=1, skipna=True) * 100
    cand_df = cand_df.drop(columns=component_cols)

    return cand_df.sort_values("Fit Score", ascending=False).reset_index(drop=True)


fit_df = compute_league_fit_scores(rec_player_id, player_seasons, con)

if fit_df.empty:
    st.info(f"Not enough data to score candidate leagues for {rec_player_name}.")
else:
    display_df = fit_df.copy()
    for c in ["Style Similarity", "League Quality (xG/90 avg)", "Avg Team PPG", "Fit Score"]:
        display_df[c] = display_df[c].round(2)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    bar_fig = go.Figure(go.Bar(
        x=fit_df["Fit Score"], y=fit_df["League"], orientation="h",
        marker_color="steelblue",
        text=[f"{v:.0f}" for v in fit_df["Fit Score"]],
        textposition="outside",
    ))
    bar_fig.update_layout(
        title=f"{rec_player_name} — league fit score by candidate destination",
        xaxis_title="Fit score (0-100, equal-weighted)", height=300,
    )
    st.plotly_chart(bar_fig, use_container_width=True)

st.caption(
    "**Roadmap:** this score currently combines only style similarity, "
    "league quality, and team ability — three of League Adaptation's "
    "own factors. It does not yet include: H2 as an injury-risk gate on "
    "the PLAYER'S CURRENT state (not the destination), H3 as an "
    "age-readiness adjustment, or H4 as a squad-composition fit check "
    "against a specific destination team. It also does not yet use "
    "model-derived weights from a combined regression — weights here "
    "are equal by construction, shown for transparency, not because "
    "they're known to be the right weights."
)