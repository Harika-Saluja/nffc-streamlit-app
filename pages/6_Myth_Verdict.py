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
    "A summary scorecard across all four tested hypotheses, plus a "
    "per-player signing score and recommendation that combines them."
)

# ===========================================================
# PART 1 — HYPOTHESIS SCORECARD
# Reads verdict_h1.json..verdict_h4.json, written independently by the
# other four pages. These are NOT the same kind of result — H1 is a
# per-player-move snapshot, H2/H4 are pooled statistical tests, H3's
# headline numbers carry a known methodology caveat. Shown side by
# side for convenience; not averaged into one number.
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
    badge = {"Positive across all metrics": "🟢", "Negative across all metrics": "🔴"}.get(verdict_text, "🟡")
    move = v.get("move", {})
    key_stat = (f"{v.get('player_name', '—')}: {move.get('from_league', '?')} "
                f"({move.get('from_season', '?')}) → {move.get('to_league', '?')} ({move.get('to_season', '?')})")
    return {"id": "H1", "name": "League Adaptation", "badge": badge, "verdict_text": verdict_text,
            "key_stat": key_stat,
            "caveat": "Per-player snapshot — reflects only the last player viewed on that page, NOT a pooled test across every player."}


def normalize_h2(v):
    if v is None:
        return None
    t1, t2 = v.get("test_1", {}), v.get("test_2", {})
    verdicts = [t1.get("verdict"), t2.get("verdict")]
    if "SUPPORTED" in verdicts:
        badge, text = "🟡", "Partially supported"
    elif verdicts and all(x == "NOT SUPPORTED" for x in verdicts if x):
        badge, text = "🟢", "Not supported"
    else:
        badge, text = "⚪", "Not computed"
    sig = t2.get("significant_predictors", [])
    return {"id": "H2", "name": "Workload & Injury Risk", "badge": badge, "verdict_text": text,
            "key_stat": f"Significant load metric(s): {', '.join(sig) if sig else 'none'}",
            "caveat": "Test 1 and Test 2 can disagree — only Test 2 found a significant metric in the reference run."}


def normalize_h3(v):
    if v is None:
        return None
    domains = v.get("method_b", {}).get("domains", {})
    peaks = ", ".join(f"{k}: {d.get('peak_age'):.1f}y" for k, d in domains.items() if d.get("peak_age") is not None)
    return {"id": "H3", "name": "Age Optimization", "badge": "⚠️", "verdict_text": "Methodology flagged — pending review",
            "key_stat": peaks or "No domain data available",
            "caveat": "The clustering behind these numbers splits sessions by z-score, then tests that SAME z-score for group differences — a structurally circular setup that can inflate significance regardless of any real age effect."}


def normalize_h4(v):
    if v is None:
        return None
    tl, il = v.get("team_level", {}), v.get("individual_level", {})
    tl_v, il_v = tl.get("verdict"), il.get("verdict")
    parts = []
    if tl_v:
        parts.append(f"Team-level: {tl_v.title()}")
    if il_v:
        parts.append(f"Individual-level: {il_v.title()}")
    badge = "🟡" if tl_v == "SIGNIFICANT RELATIONSHIP" or il_v == "SIGNIFICANT INTERACTION FOUND" else ("🟢" if tl_v or il_v else "⚪")
    rho = tl.get("spearman_rho")
    return {"id": "H4", "name": "Squad Optimizer", "badge": badge, "verdict_text": " · ".join(parts) or "Not computed",
            "key_stat": f"Diversity–PPG ρ = {rho:+.3f}" if rho is not None else "—",
            "caveat": None}


hypotheses = [normalize_h1(load_verdict("verdict_h1.json")), normalize_h2(load_verdict("verdict_h2.json")),
              normalize_h3(load_verdict("verdict_h3.json")), normalize_h4(load_verdict("verdict_h4.json"))]

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
    "averaged or combined into one score, since each uses a different "
    "test, outcome variable, and (for H1) scope."
)

# ===========================================================
# PART 2 — SIGNING SCORE ENGINE
#
# Combines a lightweight version of each hypothesis's own logic into
# one per-player score. Deliberately simplified in two places, for
# cost reasons (re-running the full pipeline per player for every
# comparison would be expensive) — documented at each simplification:
#   - Age readiness uses bucket-mean peak ages, not the full
#     clustering/ANOVA/mixed-model pipeline from Age Optimization.
#   - Injury risk uses a single recent ACWR snapshot, not the pooled
#     statistical test from Workload & Injury Risk.
# League-move quality and performance percentile reuse the same logic
# as League Adaptation directly.
# ===========================================================
st.markdown("---")
st.header("Signing Score & Recommendation")

con = duckdb.connect(database=':memory:')
con.execute("""
    CREATE TABLE lineups   AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches   AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events    AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE catapult  AS SELECT * FROM read_parquet('catapult.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
    CREATE TABLE injuries  AS SELECT * FROM read_parquet('injuries.parquet');
""")

player_seasons = con.execute("""
    WITH per_match AS (
        SELECT l.player_id, l.player_name, l.match_id, l.minutes_played,
               m.season, m.competition,
               COALESCE(e.xg_sum, 0) AS xg_sum, e.pass_success_mean,
               COALESCE(e.event_count, 0) AS event_count
        FROM lineups l
        JOIN matches m ON l.match_id = m.match_id
        LEFT JOIN events e ON e.match_id = l.match_id AND e.player_id = l.player_id
    )
    SELECT player_id, player_name, season, competition,
           SUM(minutes_played) AS minutes, SUM(xg_sum) AS xg_total,
           AVG(pass_success_mean) AS pass_success_avg, SUM(event_count) AS events_total
    FROM per_match GROUP BY player_id, player_name, season, competition
""").df()
player_seasons["xg_90"] = np.where(player_seasons["minutes"] > 0,
    player_seasons["xg_total"] / player_seasons["minutes"] * 90, np.nan)
player_seasons["events_90"] = np.where(player_seasons["minutes"] > 0,
    player_seasons["events_total"] / player_seasons["minutes"] * 90, np.nan)
STYLE_COLS = ["xg_90", "pass_success_avg", "events_90"]


def detect_all_league_switches(player_rows: pd.DataFrame):
    seasons_sorted = sorted(player_rows["season"].dropna().unique())
    switches = []
    for i in range(1, len(seasons_sorted)):
        prev_rows = player_rows[player_rows["season"] == seasons_sorted[i - 1]]
        curr_rows = player_rows[player_rows["season"] == seasons_sorted[i]]
        prev_leagues = set(prev_rows["competition"].dropna())
        curr_leagues = set(curr_rows["competition"].dropna())
        if prev_leagues and curr_leagues and not (prev_leagues & curr_leagues):
            prev_team = prev_rows["team_name"].mode()
            curr_team = curr_rows["team_name"].mode()
            switches.append({
                "from_league": list(prev_leagues)[0], "to_league": list(curr_leagues)[0],
                "from_season": seasons_sorted[i - 1], "to_season": seasons_sorted[i],
                "from_team": prev_team.iloc[0] if not prev_team.empty else None,
                "to_team": curr_team.iloc[0] if not curr_team.empty else None,
            })
    return switches


def team_ppg(team, season):
    m = con.execute(f"""
        SELECT home_team, away_team, home_score, away_score FROM matches
        WHERE season = '{season}' AND (home_team = '{team}' OR away_team = '{team}')
    """).df()
    if m.empty:
        return None
    pts = []
    for _, r in m.iterrows():
        gf, ga = (r["home_score"], r["away_score"]) if r["home_team"] == team else (r["away_score"], r["home_score"])
        pts.append(3 if gf > ga else (1 if gf == ga else 0))
    return float(np.mean(pts)) if pts else None


def league_quality(competition, season):
    comp_players = con.execute(f"""
        SELECT DISTINCT l.player_id FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE m.competition = '{competition}' AND m.season = '{season}'
    """).df()["player_id"]
    q = player_seasons[(player_seasons["season"] == season) & (player_seasons["player_id"].isin(comp_players))]
    return float(q["xg_90"].mean()) if not q.empty and q["xg_90"].notna().any() else None


def compute_league_move_component(player_id: int):
    lightweight_ps = con.execute("""
        SELECT DISTINCT l.player_id, l.team_name, m.season, m.competition
        FROM lineups l JOIN matches m ON l.match_id = m.match_id
    """).df()
    p_rows = lightweight_ps[lightweight_ps["player_id"] == player_id]
    switches = detect_all_league_switches(p_rows)
    if not switches:
        return None
    move = switches[-1]

    p_data = player_seasons[player_seasons["player_id"] == player_id]
    before = p_data[p_data["season"] == move["from_season"]]
    after = p_data[p_data["season"] == move["to_season"]]
    if before.empty or after.empty:
        return {"move": move, "score": 50.0}

    style_sim = None
    player_style = before[STYLE_COLS].iloc[0].fillna(0).values
    league_avg = player_seasons[player_seasons["season"] == move["to_season"]][STYLE_COLS].mean().fillna(0).values
    if np.linalg.norm(player_style) > 0 and np.linalg.norm(league_avg) > 0:
        style_sim = float(np.dot(player_style, league_avg) / (np.linalg.norm(player_style) * np.linalg.norm(league_avg)))

    old_ppg = team_ppg(move["from_team"], move["from_season"])
    new_ppg = team_ppg(move["to_team"], move["to_season"])
    old_q = league_quality(move["from_league"], move["from_season"])
    new_q = league_quality(move["to_league"], move["to_season"])

    pct_changes = []
    for c in STYLE_COLS:
        b, a = before[c].iloc[0], after[c].iloc[0]
        if pd.notna(b) and pd.notna(a) and b != 0:
            pct_changes.append((a - b) / abs(b))

    sub_scores = []
    if style_sim is not None:
        sub_scores.append(style_sim * 100)
    if old_ppg is not None and new_ppg is not None:
        sub_scores.append(100 if new_ppg >= old_ppg else 30)
    if pct_changes:
        sub_scores.append(min(100, max(0, 50 + float(np.mean(pct_changes)) * 100)))

    score = float(np.mean(sub_scores)) if sub_scores else 50.0
    return {
        "move": move, "score": score, "style_similarity": style_sim,
        "team_ppg": (old_ppg, new_ppg), "league_quality": (old_q, new_q),
        "avg_pct_change": float(np.mean(pct_changes)) * 100 if pct_changes else None,
    }


AGE_BANDS = [15, 23, 28, 33, 100]
AGE_BAND_LABELS = ["≤22", "23-27", "28-32", "33+"]
BUCKET_REP_AGE = {"≤22": 20, "23-27": 25, "28-32": 30, "33+": 35}


def compute_age_readiness_component(player_id: int):
    sessions = con.execute("""
        SELECT x.statsbomb_player_id AS player_id, c.date, c.v_max, c.pl_sum, c.a_sum
        FROM catapult c JOIN crosswalk x ON c.athlete_id = x.athlete_id
        WHERE x.statsbomb_player_id IS NOT NULL
    """).df()
    birth_dates = con.execute("SELECT DISTINCT player_id, birth_date FROM lineups").df()
    sessions["date"] = pd.to_datetime(sessions["date"])
    birth_dates["birth_date"] = pd.to_datetime(birth_dates["birth_date"])
    sessions = sessions.merge(birth_dates, on="player_id", how="left")
    sessions["age"] = (sessions["date"] - sessions["birth_date"]).dt.days / 365.25
    sessions = sessions.dropna(subset=["age"])

    player_sessions = sessions[sessions["player_id"] == player_id]
    if player_sessions.empty:
        return None
    player_age = player_sessions["age"].max()

    sessions["age_bucket"] = pd.cut(sessions["age"], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False)
    domain_scores = {}
    for domain, col in [("Speed", "v_max"), ("Endurance", "pl_sum"), ("Explosiveness", "a_sum")]:
        bucket_means = sessions.dropna(subset=[col]).groupby("age_bucket", observed=True)[col].mean()
        if bucket_means.empty:
            continue
        peak_bucket = str(bucket_means.idxmax())
        player_bucket = str(pd.cut([player_age], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False)[0])
        distance = abs(BUCKET_REP_AGE[peak_bucket] - BUCKET_REP_AGE[player_bucket])
        domain_scores[domain] = max(0, 100 - distance * 10)

    if not domain_scores:
        return None
    return {"player_age": float(player_age), "domain_scores": domain_scores,
            "score": float(np.mean(list(domain_scores.values())))}


def compute_injury_risk_component(player_id: int):
    sessions = con.execute(f"""
        SELECT c.date, c.sl_sum FROM catapult c
        JOIN crosswalk x ON c.athlete_id = x.athlete_id
        WHERE x.statsbomb_player_id = {player_id} ORDER BY c.date
    """).df()
    if sessions.empty or len(sessions) < 28:
        return None
    sessions["date"] = pd.to_datetime(sessions["date"])
    sessions = sessions.set_index("date")
    acute = sessions["sl_sum"].rolling("7D").sum().iloc[-1] / 7
    chronic = sessions["sl_sum"].rolling("21D").sum().iloc[-1] / 21
    if pd.isna(chronic) or chronic == 0:
        return None
    acwr = acute / chronic
    if 1.0 <= acwr <= 1.3:
        score, zone = 100, "safe"
    elif 0.8 <= acwr < 1.0 or 1.3 < acwr <= 1.5:
        score, zone = 65, "borderline"
    else:
        score, zone = 25, "high-risk"
    return {"acwr": float(acwr), "zone": zone, "score": score}


def compute_performance_percentile_component(player_id: int):
    p_data = player_seasons[player_seasons["player_id"] == player_id].sort_values("season")
    if p_data.empty:
        return None
    latest = p_data.iloc[-1]
    peers = player_seasons[
        (player_seasons["season"] == latest["season"]) & (player_seasons["competition"] == latest["competition"])
    ]["xg_90"].dropna()
    if len(peers) < 5 or pd.isna(latest["xg_90"]):
        return None
    percentile = float((peers < latest["xg_90"]).mean() * 100)
    return {"percentile": percentile, "season": latest["season"], "competition": latest["competition"],
            "score": percentile}


def compute_signing_score(player_id: int):
    league_move = compute_league_move_component(player_id)
    age = compute_age_readiness_component(player_id)
    injury = compute_injury_risk_component(player_id)
    perf = compute_performance_percentile_component(player_id)

    components = {}
    if league_move is not None:
        components["League move quality"] = league_move["score"]
    if age is not None:
        components["Age readiness"] = age["score"]
    if injury is not None:
        components["Injury-risk safety"] = injury["score"]
    if perf is not None:
        components["Current performance percentile"] = perf["score"]

    overall = float(np.mean(list(components.values()))) if components else None
    return {"overall_score": overall, "components": components,
            "league_move": league_move, "age": age, "injury": injury, "performance": perf}


with st.expander("ℹ️ How is the Signing Score calculated?"):
    st.markdown(
        "The Signing Score averages up to four components, each 0–100 "
        "— only the components a player actually has data for are "
        "included, so a player missing Catapult data is scored fairly "
        "on what's available rather than penalized for missing data:"
    )
    st.markdown(
        "- **League move quality** (League Adaptation logic) — for a "
        "player's most recent detected league move: style similarity "
        "to the new league, whether their new team out-performs their "
        "old team (points-per-game), and the % change in their own "
        "output after the move. Omitted if the player never changed "
        "leagues."
    )
    st.markdown(
        "- **Age readiness** (simplified from Age Optimization) — how "
        "close the player's current age is to the bucket with the "
        "highest average Speed/Endurance/Explosiveness in this data. "
        "**Simplified**: uses bucket averages, not the full "
        "clustering/ANOVA pipeline from that page — re-running that "
        "per player for every comparison here would be too expensive. "
        "Omitted if no Catapult data is matched."
    )
    st.markdown(
        "- **Injury-risk safety** (simplified from Workload & Injury "
        "Risk) — the player's most recent Acute:Chronic Workload Ratio "
        "(ACWR): 100 if in the 1.0–1.3 'safe' zone, 65 if borderline, "
        "25 if undertrained or spiking. **Simplified**: a single recent "
        "snapshot, not the pooled statistical test from that page. "
        "Omitted if fewer than 28 days of Catapult history exist."
    )
    st.markdown(
        "- **Current performance percentile** — the player's most "
        "recent season's xG/90, as a percentile against everyone else "
        "in their league that season."
    )
    st.markdown(
        "All available components are weighted equally and averaged. "
        "This is a transparent, equal-weighted combination — not "
        "derived from a fitted model of which factors matter most; "
        "see the caveats above for the two simplified components."
    )

players_roster = player_seasons[["player_id", "player_name"]].drop_duplicates().sort_values("player_name")

# Data/score-availability dot for these selectors: 🟢 = at least one
# signing-score component is computable (a detected league move,
# matched Catapult data, or performance data) · 🔴 = none of those
# exist for this player yet, so no score can be shown.
lightweight_ps_for_dots = con.execute("""
    SELECT DISTINCT l.player_id, l.team_name, m.season, m.competition
    FROM lineups l JOIN matches m ON l.match_id = m.match_id
""").df()
has_move_map = {pid: bool(detect_all_league_switches(g)) for pid, g in lightweight_ps_for_dots.groupby("player_id")}

matched_catapult_ids = set(con.execute("""
    SELECT DISTINCT x.statsbomb_player_id AS player_id
    FROM catapult c JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id IS NOT NULL
""").df()["player_id"])

perf_ids = set(player_seasons.loc[player_seasons["xg_90"].notna(), "player_id"])


def has_any_score_data(pid: int) -> bool:
    return has_move_map.get(pid, False) or (pid in matched_catapult_ids) or (pid in perf_ids)


players_roster["has_score"] = players_roster["player_id"].apply(has_any_score_data)
players_roster["display_label"] = players_roster["player_name"] + players_roster["has_score"].map({True: " 🟢", False: " 🔴"})

DOT_LEGEND = "🟢 : enough data to compute a signing score · 🔴 : not enough data yet"


def resolve_player(label: str):
    row = players_roster.loc[players_roster["display_label"] == label]
    return int(row["player_id"].iloc[0]), row["player_name"].iloc[0]


def render_player_recommendation(pid: int, pname: str):
    result = compute_signing_score(pid)
    overall = result["overall_score"]

    if overall is None:
        st.info(f"Not enough data to compute a signing score for {pname}.")
        return result

    if overall >= 70:
        badge, verdict_word = "🟢", "Strong signing case"
    elif overall >= 45:
        badge, verdict_word = "🟡", "Mixed signing case"
    else:
        badge, verdict_word = "🔴", "Weak signing case"

    st.metric(f"{pname} — Signing Score", f"{badge} {overall:.0f} / 100 — {verdict_word}")

    comp_df = pd.DataFrame([{"Component": k, "Score": v} for k, v in result["components"].items()])
    bar_fig = go.Figure(go.Bar(
        x=comp_df["Score"], y=comp_df["Component"], orientation="h",
        marker_color=["seagreen" if v >= 70 else "goldenrod" if v >= 45 else "crimson" for v in comp_df["Score"]],
        text=[f"{v:.0f}" for v in comp_df["Score"]], textposition="outside",
    ))
    bar_fig.update_layout(title=f"{pname} — component breakdown", xaxis_title="Score (0-100)", height=250)
    st.plotly_chart(bar_fig, use_container_width=True)

    lines = []
    lm = result["league_move"]
    if lm is not None:
        move = lm["move"]
        direction = "a good decision" if lm["score"] >= 60 else ("a mixed decision" if lm["score"] >= 40 else "a questionable decision")
        lines.append(
            f"**League move:** moved from {move['from_league']} to "
            f"{move['to_league']} ({move['from_season']} → {move['to_season']}) "
            f"— based on style fit, team strength change, and post-move "
            f"performance, this looks like **{direction}** "
            f"(component score {lm['score']:.0f}/100)."
        )
    else:
        lines.append("**League move:** no detected league change in this dataset's tracked window.")

    age = result["age"]
    if age is not None:
        lines.append(
            f"**Age readiness:** currently {age['player_age']:.1f} years "
            f"old, scoring {age['score']:.0f}/100 against the age bucket "
            f"with the strongest average physical output in this data."
        )

    injury = result["injury"]
    if injury is not None:
        lines.append(f"**Injury risk:** most recent training load sits in the **{injury['zone']}** zone (ACWR ≈ {injury['acwr']:.2f}).")

    perf = result["performance"]
    if perf is not None:
        lines.append(
            f"**Current performance:** {perf['percentile']:.0f}th "
            f"percentile on xG/90 in {perf['competition']} ({perf['season']})."
        )

    for line in lines:
        st.markdown(f"- {line}")

    return result


tab1, tab2 = st.tabs(["Single Player", "Compare Two Players"])

with tab1:
    st.caption(DOT_LEGEND)
    single_label = st.selectbox("Player:", players_roster["display_label"], key="single_player")
    single_id, single_name = resolve_player(single_label)
    render_player_recommendation(single_id, single_name)

with tab2:
    st.caption(DOT_LEGEND)
    col_a, col_b = st.columns(2)
    with col_a:
        label_a = st.selectbox("Player A:", players_roster["display_label"], key="compare_a")
    with col_b:
        _, name_a_temp = resolve_player(label_a)
        remaining = players_roster[players_roster["player_name"] != name_a_temp]
        label_b = st.selectbox("Player B:", remaining["display_label"], key="compare_b")

    id_a, name_a = resolve_player(label_a)
    id_b, name_b = resolve_player(label_b)

    col_a, col_b = st.columns(2)
    with col_a:
        result_a = render_player_recommendation(id_a, name_a)
    with col_b:
        result_b = render_player_recommendation(id_b, name_b)

    st.markdown("---")
    if result_a["overall_score"] is not None and result_b["overall_score"] is not None:
        if result_a["overall_score"] > result_b["overall_score"]:
            better, worse, b_score, w_score = name_a, name_b, result_a["overall_score"], result_b["overall_score"]
        elif result_b["overall_score"] > result_a["overall_score"]:
            better, worse, b_score, w_score = name_b, name_a, result_b["overall_score"], result_a["overall_score"]
        else:
            better = worse = None

        if better:
            st.success(
                f"**{better}** looks like the stronger signing case than "
                f"**{worse}** in this data ({b_score:.0f} vs. {w_score:.0f}) "
                f"— see the component breakdowns above for exactly where "
                f"the gap comes from."
            )
        else:
            st.info(f"{name_a} and {name_b} score essentially the same overall ({result_a['overall_score']:.0f}).")
    else:
        st.info("Not enough data on one or both players to compare directly.")

st.caption(
    "This score combines lightweight proxies from across all four "
    "hypothesis pages — it is a convenience readout for exploring "
    "trade-offs between players, not a validated recruitment model."
)