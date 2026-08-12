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
st.set_page_config(page_title="Player Profile Dashboard", layout="wide")
st.title("PLAYER PROFILE")

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups   AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches   AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events    AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE injuries  AS SELECT * FROM read_parquet('injuries.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
    CREATE TABLE catapult  AS SELECT * FROM read_parquet('catapult.parquet');
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
# Player bio, with full career history (recent -> past)
# -------------------------------
bio = con.execute(f"""
    SELECT player_id, player_name, birth_date
    FROM lineups
    WHERE player_id = {player_id}
    LIMIT 1
""").df()

career_history = con.execute(f"""
    SELECT DISTINCT m.season, m.competition, l.team_name
    FROM lineups l
    JOIN matches m ON l.match_id = m.match_id
    WHERE l.player_id = {player_id}
    ORDER BY m.season DESC
""").df()

if bio.empty:
    st.info("No bio data available for this player.")
else:
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Player ID:** {int(bio['player_id'].iloc[0])}")
        st.write(f"**Birth Date:** {bio['birth_date'].iloc[0]}")
    with col2:
        st.write("**Teams & Leagues (most recent first):**")
        if career_history.empty:
            st.write("—")
        else:
            for _, row in career_history.iterrows():
                st.write(f"- {row['season']}: **{row['team_name']}** ({row['competition']})")

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

birth_date_val = pd.to_datetime(bio["birth_date"].iloc[0]) if not bio.empty and pd.notna(bio["birth_date"].iloc[0]) else None
current_age = (pd.Timestamp.now() - birth_date_val).days / 365.25 if birth_date_val is not None else None

n_league_moves = max(0, career_history["competition"].nunique() - 1) if not career_history.empty else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Matches Played", int(summary["matches_played"].iloc[0]))
minutes_val = summary["total_minutes"].iloc[0]
col2.metric("Minutes Played", int(minutes_val) if pd.notna(minutes_val) else 0)
col3.metric("Injury Days", int(injury_days["injury_days"].iloc[0]))
col4.metric("Current Age", f"{current_age:.1f}" if current_age is not None else "—")
col5.metric("League Moves", n_league_moves)

# ---------------------------------------------------------
# VERDICT SUMMARY — one real result per hypothesis, read from
# verdict_h1.json..verdict_h4.json (written by the four other pages).
# ---------------------------------------------------------
st.markdown("---")
st.header("Verdict Summary")


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
    return {"name": "H1: League Adaptation", "badge": badge, "verdict_text": verdict_text, "key_stat": key_stat,
            "help": ("Tests whether a player's performance changes after a cross-league move. "
                     "This result is a PER-PLAYER snapshot — whichever player was last viewed "
                     "on that page — not a pooled test across everyone.\n\n" + key_stat)}


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
    return {"name": "H2: Workload & Injury Risk", "badge": badge, "verdict_text": text,
            "key_stat": f"Significant load metric(s): {', '.join(sig) if sig else 'none'}",
            "help": ("Tests whether higher training load before an injury is associated with "
                     "increased injury likelihood, pooled across every player. "
                     f"Significant load metric(s): {', '.join(sig) if sig else 'none'}.")}


def normalize_h3(v):
    if v is None:
        return None
    domains = v.get("method_b", {}).get("domains", {})
    peaks = ", ".join(f"{k}: {d.get('peak_age'):.1f}y" for k, d in domains.items() if d.get("peak_age") is not None)
    return {"name": "H3: Age Optimization", "badge": "⚠️", "verdict_text": "Methodology flagged — pending review",
            "key_stat": peaks or "No domain data available",
            "help": ("Tests whether physical performance peaks at a particular age. "
                     "The clustering behind these numbers has a known circularity issue "
                     "(it splits sessions by the same z-score it then tests), so treat "
                     f"the headline peak ages with caution: {peaks or 'no data'}.")}


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
    return {"name": "H4: Squad Balance", "badge": badge, "verdict_text": " · ".join(parts) or "Not computed",
            "key_stat": f"Diversity–PPG ρ = {rho:+.3f}" if rho is not None else "—",
            "help": ("Tests whether squad nationality diversity relates to results (team-level), "
                     "and whether being a foreign newcomer predicts performance (individual-level). "
                     f"Diversity–PPG correlation: ρ={rho:+.3f}." if rho is not None else
                     "Tests squad diversity vs. results, and foreign-newcomer performance patterns.")}


hyp_results = [normalize_h1(load_verdict("verdict_h1.json")), normalize_h2(load_verdict("verdict_h2.json")),
               normalize_h3(load_verdict("verdict_h3.json")), normalize_h4(load_verdict("verdict_h4.json"))]

for h in hyp_results:
    if h is None:
        continue
    st.metric(h["name"], f"{h['badge']} {h['verdict_text']}", help=h["help"])
    st.caption(h["key_stat"])

if all(h is None for h in hyp_results):
    st.info("No hypothesis verdicts have been computed yet — visit each of the four other pages at least once.")

# ---------------------------------------------------------
# PERFECT SIGNING SCORE
# Combines a lightweight version of each hypothesis's own logic — see
# the formula breakdown below for exactly what's included and why two
# of the four components are deliberately simplified.
# ---------------------------------------------------------
st.markdown("---")
st.header("Perfect Signing Score")

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


def compute_league_move_component(pid: int):
    lightweight_ps = con.execute("""
        SELECT DISTINCT l.player_id, l.team_name, m.season, m.competition
        FROM lineups l JOIN matches m ON l.match_id = m.match_id
    """).df()
    p_rows = lightweight_ps[lightweight_ps["player_id"] == pid]
    switches = detect_all_league_switches(p_rows)
    if not switches:
        return None
    move = switches[-1]

    p_data = player_seasons[player_seasons["player_id"] == pid]
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
    return {"move": move, "score": score}


AGE_BANDS = [15, 23, 28, 33, 100]
AGE_BAND_LABELS = ["≤22", "23-27", "28-32", "33+"]
BUCKET_REP_AGE = {"≤22": 20, "23-27": 25, "28-32": 30, "33+": 35}


def compute_age_readiness_component(pid: int):
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

    player_sessions = sessions[sessions["player_id"] == pid]
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


def compute_injury_risk_component(pid: int):
    sessions = con.execute(f"""
        SELECT c.date, c.sl_sum FROM catapult c
        JOIN crosswalk x ON c.athlete_id = x.athlete_id
        WHERE x.statsbomb_player_id = {pid} ORDER BY c.date
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


def compute_performance_percentile_component(pid: int):
    p_data = player_seasons[player_seasons["player_id"] == pid].sort_values("season")
    if p_data.empty:
        return None
    latest = p_data.iloc[-1]
    peers = player_seasons[
        (player_seasons["season"] == latest["season"]) & (player_seasons["competition"] == latest["competition"])
    ]["xg_90"].dropna()
    if len(peers) < 5 or pd.isna(latest["xg_90"]):
        return None
    percentile = float((peers < latest["xg_90"]).mean() * 100)
    return {"percentile": percentile, "season": latest["season"], "competition": latest["competition"], "score": percentile}


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

overall_score = float(np.mean(list(components.values()))) if components else None

with st.expander("ℹ️ How is this score calculated?"):
    st.markdown(
        "Averages up to four components, each 0–100 — only the "
        "components this player actually has data for are included, "
        "so missing data (e.g. no Catapult sessions) doesn't penalize "
        "the score, it just narrows what's averaged:"
    )
    st.markdown(
        "- **League move quality** — for this player's most recent "
        "detected league move: style similarity to the new league, "
        "whether their new team out-performs their old team, and their "
        "own % performance change after the move. Omitted if they've "
        "never changed leagues."
    )
    st.markdown(
        "- **Age readiness** *(simplified)* — how close their current "
        "age is to the age bucket with the strongest average physical "
        "output in this data. Uses bucket averages rather than the "
        "full clustering/ANOVA pipeline from Age Optimization, for "
        "computational cost reasons."
    )
    st.markdown(
        "- **Injury-risk safety** *(simplified)* — their most recent "
        "Acute:Chronic Workload Ratio (ACWR): 100 if in the 1.0–1.3 "
        "'safe' zone, 65 if borderline, 25 if undertrained or spiking. "
        "A single recent snapshot, not the pooled statistical test "
        "from Workload & Injury Risk."
    )
    st.markdown(
        "- **Current performance percentile** — their most recent "
        "season's xG/90, as a percentile against everyone else in "
        "their league that season."
    )
    st.markdown(
        "All available components are weighted equally and averaged — "
        "a transparent combination, not derived from a fitted model of "
        "which factors matter most."
    )

if overall_score is None:
    st.info("Not enough data available to compute a signing score for this player.")
else:
    if overall_score >= 70:
        badge, verdict_word = "🟢", "Strong signing case"
    elif overall_score >= 45:
        badge, verdict_word = "🟡", "Mixed signing case"
    else:
        badge, verdict_word = "🔴", "Weak signing case"

    st.metric("Perfect Signing Score", f"{badge} {overall_score:.0f} / 100 — {verdict_word}")

    comp_df = pd.DataFrame([{"Component": k, "Score": v} for k, v in components.items()])
    bar_fig = go.Figure(go.Bar(
        x=comp_df["Score"], y=comp_df["Component"], orientation="h",
        marker_color=["seagreen" if v >= 70 else "goldenrod" if v >= 45 else "crimson" for v in comp_df["Score"]],
        text=[f"{v:.0f}" for v in comp_df["Score"]], textposition="outside",
    ))
    bar_fig.update_layout(title=f"{player_name} — component breakdown", xaxis_title="Score (0-100)", height=250)
    st.plotly_chart(bar_fig, use_container_width=True)

    if league_move is not None:
        move = league_move["move"]
        direction = "a good decision" if league_move["score"] >= 60 else ("a mixed decision" if league_move["score"] >= 40 else "a questionable decision")
        st.caption(
            f"Their move from {move['from_league']} to {move['to_league']} "
            f"looks like **{direction}** based on style fit, team "
            f"strength, and post-move performance."
        )