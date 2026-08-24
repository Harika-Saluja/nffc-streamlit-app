import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
from datetime import datetime, timezone

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="League Adaptation", layout="wide")
st.title("LEAGUE ADAPTATION")

#st.caption(
#    "Data source: StatsBomb open/provided match, lineup, and event data "
 #   "spanning multiple competitions and clubs — not a Nottingham Forest-"
  #  "exclusive feed. Nottingham Forest is used throughout this dashboard "
   # "as the case-study club within that broader dataset; players from "
   # "other clubs are also selectable below since league-quality and "
   # "percentile calculations require the full multi-club distribution."
#)

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

metric_map = {
    "xG per 90": ("xg_90", "xG / 90"),
    "Pass Success %": ("pass_success_avg", "Pass success (mean probability)"),
    "Events per 90": ("events_90", "Events / 90"),
}
# Factor 3 ("league quality") is part of the fixed four-factor breakdown,
# not something the reader should be able to toggle, so it uses a fixed
# metric rather than following the page-scoped Panel-d selector.
QUALITY_METRIC_COL, QUALITY_METRIC_LABEL = metric_map["xG per 90"]

# Shared definitions for the three underlying per-90 metrics, reused
# everywhere they're shown so the same explanation appears wherever a
# "?" tooltip can attach to a real widget.
METRIC_DEFINITIONS = {
    "xG per 90": (
        "**xG per 90** — Expected Goals per 90 minutes: the sum of shot "
        "quality (xG) across a player's matches that season, divided by "
        "total minutes played, scaled to a 90-minute rate. Reflects "
        "shot-quality/attacking threat, independent of whether the shots "
        "actually scored."
    ),
    "Pass Success %": (
        "**Pass Success %** — despite the name, not a literal completion "
        "percentage: it's the average, across the player's matches that "
        "season, of each match's own mean pass-success probability — an "
        "average of match-level averages, not weighted by how many "
        "passes were actually attempted in each match."
    ),
    "Events per 90": (
        "**Events per 90** — total recorded on-ball events (any touch or "
        "action), summed across the player's matches that season, "
        "divided by total minutes, scaled to a 90-minute rate. A rough "
        "volume/involvement proxy — not weighted by event type or value."
    ),
}
METRIC_DEFINITIONS_HELP = "\n\n".join(METRIC_DEFINITIONS.values())

# -------------------------------
# Sidebar – full player roster, with a move indicator per player
# -------------------------------
st.sidebar.title("Player Selector")

players = player_seasons[["player_id", "player_name"]].drop_duplicates().sort_values("player_name")
if players.empty:
    st.error("No players found in lineups.parquet.")
    st.stop()


def detect_all_league_switches(pdata: pd.DataFrame):
    """Every genuine league switch across this player's tracked seasons —
    a competition change between two consecutive seasons. Returns a list
    (possibly empty, possibly with more than one entry for a player who
    has changed leagues more than once)."""
    seasons_sorted = sorted(pdata["season"].dropna().unique())
    switches = []
    for i in range(1, len(seasons_sorted)):
        prev_leagues = set(pdata[pdata["season"] == seasons_sorted[i - 1]]["competition"].dropna())
        curr_leagues = set(pdata[pdata["season"] == seasons_sorted[i]]["competition"].dropna())
        if prev_leagues and curr_leagues and not (prev_leagues & curr_leagues):
            switches.append({
                "from_league": list(prev_leagues)[0],
                "to_league": list(curr_leagues)[0],
                "from_season": seasons_sorted[i - 1],
                "to_season": seasons_sorted[i],
            })
    return switches


# Precompute, for EVERY player, whether any cross-league move is
# detected across their tracked seasons — used only to decorate the
# sidebar selector (🟢 = moved, 🔵 = no detected move in this window).
# Uses a plain dict comprehension (not groupby().apply(...,
# include_groups=False)) since that kwarg needs pandas 2.2+ and this
# needs to run on whatever pandas version is actually deployed.
move_status = pd.Series(
    {pid: bool(detect_all_league_switches(g)) for pid, g in player_seasons.groupby("player_id")},
    name="has_move",
)
move_status.index.name = "player_id"
players = players.merge(move_status, on="player_id", how="left")
players["has_move"] = players["has_move"].fillna(False)
# NOTE: changed the "no move" indicator from 🔴 to 🔵 — red implied
# something negative/broken about the player, when it just means
# "stayed in one league," which is the normal case for most players.
players["display_label"] = players["player_name"] + players["has_move"].map({True: " 🟢", False: " 🔵"})

selected_label = st.sidebar.selectbox("Select Player", players["display_label"])
st.sidebar.caption("🟢 : moved leagues within the tracked window · 🔵 : no detected move — current league shown instead")

matched = players.loc[players["display_label"] == selected_label]
if matched.empty:
    st.error("Selected player not found.")
    st.stop()
player_id = int(matched["player_id"].iloc[0])
player_name = matched["player_name"].iloc[0]

st.markdown("---")

player_data = player_seasons[player_seasons["player_id"] == player_id].sort_values("season")

if player_data.empty:
    st.info(f"No season data available for {player_name}.")
    st.stop()

# -------------------------------
# Player header: name + earliest tracked date + full league history
# -------------------------------
st.header(player_name)

career_start_row = con.execute(f"""
    SELECT MIN(m.match_date) AS start_date
    FROM lineups l JOIN matches m ON l.match_id = m.match_id
    WHERE l.player_id = {player_id}
""").df()
career_start_date = career_start_row["start_date"].iloc[0]
career_start_str = (
    pd.to_datetime(career_start_date).strftime("%d %b %Y")
    if pd.notna(career_start_date) else "unknown"
)
st.caption(
    f"Tracked in this dataset since **{career_start_str}** — earliest "
    f"recorded match in this data, not necessarily their actual career debut."
)

all_switches = detect_all_league_switches(player_data)

# ===========================================================
# NO DETECTED MOVE — show a current-league snapshot instead of
# stopping the page. This is the common case (most players in any
# dataset haven't switched leagues within the tracked window), so a
# dead-end message here made the dashboard unusable for the large
# majority of players. Instead: show their current club, competition,
# season, and per-90 profile, plus where they sit in their own
# league's distribution — the same percentile mechanic used for
# movers in the Detailed Move Analysis section below, just without a
# before/after comparison since there's no "before" to compare to.
# ===========================================================
if not all_switches:
    latest_season = player_data["season"].dropna().max()
    current = player_data[player_data["season"] == latest_season]

    if current.empty:
        st.info(f"No usable season data available for {player_name}.")
        st.stop()

    current_row = current.iloc[0]
    current_league = current_row["competition"]

    current_team_row = con.execute(f"""
        SELECT l.team_name, COUNT(DISTINCT l.match_id) AS n_matches
        FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE l.player_id = {player_id} AND m.season = '{latest_season}'
        GROUP BY l.team_name ORDER BY n_matches DESC LIMIT 1
    """).df()
    current_team = current_team_row["team_name"].iloc[0] if not current_team_row.empty else "unknown club"

    st.info(
        f"**{player_name} hasn't changed leagues within this dataset's "
        f"tracked window.** They remain at **{current_team}** in the "
        f"**{current_league}** ({latest_season}) — shown below is their "
        f"current-league snapshot rather than a before/after move "
        f"comparison, since there's no prior league to compare against."
    )

    st.subheader(f"Current League Snapshot — {current_league} ({latest_season})")

    snap_cols = st.columns(3)
    for i, (label_key, (col, disp_label)) in enumerate(metric_map.items()):
        val = current_row[col]
        snap_cols[i].metric(
            disp_label,
            f"{val:.2f}" if pd.notna(val) else "—",
            help=METRIC_DEFINITIONS[label_key],
        )

    # Percentile within their current league — same mechanic as the
    # "Where This Player Sits vs. the New League" panel for movers,
    # just relabelled since there's no "new" league here, only their
    # current one.
    st.markdown("---")
    st.subheader("Where This Player Sits vs. Their League")

    snap_metric_choice = st.radio(
        "Chart metric:", list(metric_map.keys()), horizontal=True,
        key="snapshot_metric", help=METRIC_DEFINITIONS_HELP,
    )
    snap_col, snap_label = metric_map[snap_metric_choice]

    snap_dist = player_seasons[
        (player_seasons["season"] == latest_season)
        & (player_seasons["competition"] == current_league)
    ][snap_col].dropna()

    if len(snap_dist) < 5:
        st.info("Not enough players in this league/season to build a distribution.")
    else:
        snap_value = current_row[snap_col]
        if pd.notna(snap_value):
            snap_percentile = float((snap_dist < snap_value).mean() * 100)

            snap_fig = go.Figure()
            snap_fig.add_trace(go.Box(
                x=snap_dist, name=current_league, boxpoints="all",
                jitter=0.6, pointpos=0, marker_color="lightgray", line_color="lightgray",
                fillcolor="rgba(0,0,0,0)",
            ))
            snap_fig.add_trace(go.Scatter(
                x=[snap_value], y=[current_league],
                mode="markers", marker=dict(size=16, color="steelblue", symbol="diamond"),
                name=player_name,
            ))
            snap_fig.update_layout(
                title=f"{snap_label} vs. all {current_league} players ({latest_season})",
                xaxis_title=snap_label, height=250, showlegend=True,
            )
            st.plotly_chart(snap_fig, use_container_width=True)

            st.metric(
                f"{snap_label} percentile",
                f"{snap_percentile:.0f}th percentile",
                help=(
                    "**What it is:** where the player's value on this "
                    "metric ranks against every other player in their "
                    "current league that season.\n\n"
                    "**How it's calculated:** the share of the league's "
                    "players whose value was LOWER than this player's, "
                    "× 100.\n\n" + METRIC_DEFINITIONS[snap_metric_choice]
                ),
            )
        else:
            st.info(f"{player_name} has no recorded {snap_label} value to compare.")

    st.markdown("---")

    # Save a scoped verdict for the Myth Verdict dashboard even for
    # non-movers — same JSON shape as the mover path below, but with
    # the move-specific fields set to None and an explicit "no_move"
    # flag so the Myth Verdict page can distinguish and label these
    # correctly rather than mishandling missing keys.
    h1_verdict_record = {
        "hypothesis": "H1 — League Adaptation",
        "scope": (
            "per-player, current-league snapshot (no detected league "
            "move) — NOT a pooled population-level test like H2/H3/H4; "
            "no before/after comparison is possible for this player."
        ),
        "player_name": player_name,
        "player_id": player_id,
        "no_move_detected": True,
        "current_club": current_team,
        "current_league": current_league,
        "current_season": latest_season,
        "n_total_tracked_moves_for_player": 0,
        "performance_change_verdict": None,
        "style_similarity": None,
        "team_ability_ppg": None,
        "league_quality_proxy": None,
        "same_role": None,
        "destination_percentile": None,
        "data_confidence": None,
        "last_computed": datetime.now(timezone.utc).isoformat(),
    }
    with open("verdict_h1.json", "w") as f:
        json.dump(h1_verdict_record, f, indent=2, default=str)

    st.stop()

# ===========================================================
# BELOW THIS POINT: unchanged mover path — a genuine league switch
# was detected, so the full four-factor breakdown and Detailed Move
# Analysis run as before.
# ===========================================================

sequence_parts = [f"{all_switches[0]['from_league']} ({all_switches[0]['from_season']})"]
for sw in all_switches:
    sequence_parts.append(f"{sw['to_league']} ({sw['to_season']})")
st.success("**League history:** " + " → ".join(sequence_parts))

if len(all_switches) > 1:
    move_options = [
        f"{sw['from_league']} ({sw['from_season']}) → {sw['to_league']} ({sw['to_season']})"
        for sw in all_switches
    ]
    selected_move_idx = st.selectbox(
        "Which move should the detailed analysis below focus on?",
        options=list(range(len(move_options))),
        format_func=lambda i: move_options[i],
        index=len(move_options) - 1,  # default: most recent move
    )
    league_switch = all_switches[selected_move_idx]
else:
    league_switch = all_switches[0]

before = player_data[player_data["season"] == league_switch["from_season"]]
after = player_data[player_data["season"] == league_switch["to_season"]]

# ===========================================================
# FOUR-FACTOR BREAKDOWN
# ===========================================================
st.header("Four-Factor Breakdown")

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
    help=(
        "**What it is:** cosine similarity between two 3-value vectors — "
        "the player's own (xG/90, pass success %, events/90) from their "
        "final season before the move, and the league-wide average of "
        "those same three numbers in the destination league in  that season.\n\n"
        "**How it's calculated:** cos(θ) = (A·B) / (|A|·|B|), where A is "
        "the player's vector and B is the league-average vector. Ranges "
        "0–1; closer to 1 means the two vectors point in a similar "
        "direction. Note the three inputs are on very different raw "
        "scales (events/90 is typically much larger than pass success % "
        "or xG/90), which can pull this toward whichever input has the "
        "largest magnitude rather than true stylistic fit."
    ),
)
c2.metric(
    "2. Team ability (PPG)",
    f"{old_team_ppg:.2f} → {new_team_ppg:.2f}"
    if old_team_ppg is not None and new_team_ppg is not None else "—",
    help=(
        "**What it is:** points-per-game of the old team vs. the new "
        "team, that season.\n\n"
        "**How it's calculated:** 3 points for a win, 1 for a draw, 0 "
        "for a loss, averaged across every match each team played that "
        "season (from actual match results) — not adjusted for opponent "
        "strength or league difficulty."
    ),
)
c3.metric(
    "3. League quality (proxy)",
    f"{old_league_quality:.2f} → {new_league_quality:.2f}"
    if old_league_quality is not None and new_league_quality is not None else "—",
    help=(
        f"**What it is:** league-wide average {QUALITY_METRIC_LABEL} — "
        f"always uses this one fixed metric, regardless of what's picked "
        f"further down the page.\n\n"
        f"**How it's calculated:** the mean {QUALITY_METRIC_LABEL} across "
        f"every player who appeared in that competition that season. A "
        f"rough proxy for league strength, not a validated rating — it's "
        f"confounded with playing style (an expansive, attack-minded "
        f"league reads higher here even if it isn't objectively stronger)."
    ),
)
c4.metric(
    "4. Same role?",
    "Yes" if same_position else ("No" if same_position is not None else "—"),
    help=(
        "**What it is:** whether the player's most common tracked "
        "position matches before vs. after the move.\n\n"
        "**How it's calculated:** the single `primary_position` value "
        "logged most often across the player's matches in each season "
        "(the position they played in the most that season) — compared "
        "directly as text, old vs. new."
        + (f"\n\n**Values:** {old_pos_val or '—'} → {new_pos_val or '—'}" if has_position else "")
    ),
)

# ===========================================================
# DETAILED MOVE ANALYSIS
# Mirrors Dinsdale & Gallagher (2022) Figure 1's panel layout, adapted
# to what this project's data can actually support.
# ===========================================================
st.markdown("---")
st.header("Detailed Move Analysis")

all_metric_cols = ["xg_90", "pass_success_avg", "events_90"]
all_metric_labels = {"xg_90": "xG / 90", "pass_success_avg": "Pass Success %", "events_90": "Events / 90"}

# --- Predicted performance change ---
st.subheader("Predicted Player Performance Change")

with st.expander("ℹ️ What do xG/90, Pass Success %, and Events/90 mean?"):
    for definition in METRIC_DEFINITIONS.values():
        st.markdown(definition)

if before.empty or after.empty:
    st.info("Missing before/after data for this move.")
    pct_rows = []
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
            title=(
                f"Predicted % change per metric from "
                f"{league_switch['from_league']} to {league_switch['to_league']}"
            ),
            xaxis_title="% change (before → after move)",
            height=300,
        )
        st.plotly_chart(bar_fig, use_container_width=True)

        all_positive = all(r["pct_change"] > 0 for r in pct_rows)
        all_negative = all(r["pct_change"] < 0 for r in pct_rows)
        if all_positive:
            verdict_a, badge_a, short_verdict = "Positive across all metrics", "🟢", "Positive"
            verdict_detail = "Every tracked metric improved after the move."
        elif all_negative:
            verdict_a, badge_a, short_verdict = "Negative across all metrics", "🔴", "Negative"
            verdict_detail = "Every tracked metric declined after the move."
        else:
            verdict_a, badge_a, short_verdict = (
                "Mixed — improved on some metrics, declined on others", "🟡", "Mixed",
            )
            verdict_detail = "Some tracked metrics improved after the move while others declined."

        # NOTE: st.metric's value field truncates long text with an
        # ellipsis and does not wrap — keeping the metric value short
        # (badge + one word) and putting the full explanation in a
        # st.caption underneath (smaller font than the metric number,
        # wraps normally onto multiple lines) avoids that truncation.
        st.metric(
            "Verdict",
            f"{badge_a} {short_verdict}",
            help=(
                "**What it is:** a simple summary of the bars above.\n\n"
                "**How it's calculated:** 🟢 = every metric's bar is "
                "positive (all improved after the move). 🔴 = every "
                "metric's bar is negative (all declined). 🟡 = a mix "
                "of positive and negative bars. Based only on the "
                "sign of each % change, not its size — a small +2% "
                "counts the same as a large +77% here."
            ),
        )
        st.caption(verdict_detail)
    else:
        st.info("Not enough non-zero data to compute % change.")

st.markdown("---")

# --- Data confidence (stacked below, not side-by-side — the two-column
# layout was cutting off text on narrower screens) ---
st.subheader("Data Confidence")

def rag_status(n_matches: int) -> tuple[str, str]:
    if n_matches >= 15:
        return "🟢", "Green"
    elif n_matches >= 5:
        return "🟡", "Amber"
    else:
        return "🔴", "Red"

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

confidence_rows = [
    (player_name, player_n_matches, "player's own matches this season"),
    (league_switch["from_league"], old_league_n, "matches in origin league"),
    (league_switch["to_league"], new_league_n, "matches in destination league"),
]
statuses = []
for label_txt, n_val, threshold_note in confidence_rows:
    badge, status_word = rag_status(int(n_val))
    statuses.append(status_word)
    st.write(f"{badge} **{label_txt}**")
    st.caption(f"{int(n_val)} {threshold_note} — {status_word} confidence")

if all(s == "Green" for s in statuses):
    overall_conf_word, overall_conf_badge = "High", "🟢"
    overall_conf_note = "All three sample sizes are comfortably large — these numbers aren't resting on a handful of matches."
elif any(s == "Red" for s in statuses):
    overall_conf_word, overall_conf_badge = "Low", "🔴"
    overall_conf_note = "At least one of the three samples above is small — treat this move's numbers with extra caution."
else:
    overall_conf_word, overall_conf_badge = "Moderate", "🟡"
    overall_conf_note = "Sample sizes are adequate but not large across the board — reasonable confidence, not full confidence."

st.metric(
    "Overall data confidence",
    f"{overall_conf_badge} {overall_conf_word}",
    help=(
        "**What it is:** a data-volume check, not a judgment on "
        "whether the move itself was good — it only asks 'is there "
        "enough underlying data to trust the numbers on this page.'\n\n"
        "**How it's calculated:** each of the three counts above is "
        "graded 🟢 15+ matches, 🟡 5–14, 🔴 <5. Overall confidence is "
        "🟢 only if all three are green, 🔴 if any one is red, "
        "otherwise 🟡."
    ),
)
st.caption(overall_conf_note)

st.markdown("---")

# --- Where this player sits vs. the new league ---
st.subheader("Where This Player Sits vs. the New League")

panel_d_metric_choice = st.radio(
    "Chart metric (this chart only):",
    ["xG per 90", "Pass Success %", "Events per 90"],
    horizontal=True,
    key="panel_d_metric",
    help=METRIC_DEFINITIONS_HELP,
)
col, label = metric_map[panel_d_metric_choice]

dist_data = player_seasons[
    (player_seasons["season"] == league_switch["to_season"])
    & (player_seasons["competition"] == league_switch["to_league"])
][col].dropna()

percentile = None
player_value = None

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
            title=f"{label} vs. all {league_switch['to_league']} players ({league_switch['to_season']})",
            xaxis_title=label, height=250, showlegend=True,
        )
        st.plotly_chart(strip_fig, use_container_width=True)

        st.metric(
            f"{label} percentile",
            f"{percentile:.0f}th percentile",
            help=(
                "**What it is:** where the player's value on this metric "
                "ranks against every other player in the destination "
                "league that season (the gray dots above).\n\n"
                "**How it's calculated:** the share of the destination "
                "league's players whose value was LOWER than this "
                "player's, × 100. E.g. 94th percentile = higher than 94 "
                "out of 100 players in that league on this metric.\n\n"
                + METRIC_DEFINITIONS[panel_d_metric_choice]
            ),
        )
        if percentile >= 75:
            interp = "This places them near the top of the distribution for this metric in their new league."
        elif percentile >= 40:
            interp = "This places them around the middle of the pack for this metric in their new league."
        else:
            interp = "This places them in the lower portion of the distribution for this metric in their new league."
        st.caption(interp)
    else:
        st.info(f"{player_name} has no recorded {label} value after the move to compare.")

st.markdown("---")

# ===========================================================
# SAVE VERDICT — for the Myth Verdict summary dashboard
#
# IMPORTANT SCOPE NOTE: unlike H2/H3/H4 (Mann-Whitney U, logistic
# regression, ANOVA — each pooled across every player), this page is
# fundamentally PER-PLAYER and PER-MOVE. This JSON necessarily reflects
# only whichever player is currently selected in the sidebar, not a
# population-level statistical test. It should be displayed on Myth
# Verdict as "most recently viewed player move," not averaged/compared
# against the other three hypotheses' pooled verdicts as if equivalent.
# ===========================================================
h1_verdict_record = {
    "hypothesis": "H1 — League Adaptation",
    "scope": (
        "per-player-move (last viewed in this dashboard) — NOT a pooled "
        "population-level test like H2/H3/H4; this evaluates one "
        "player's one detected move only."
    ),
    "player_name": player_name,
    "player_id": player_id,
    "no_move_detected": False,
    "move": {
        "from_league": league_switch["from_league"],
        "from_season": league_switch["from_season"],
        "to_league": league_switch["to_league"],
        "to_season": league_switch["to_season"],
    },
    "n_total_tracked_moves_for_player": len(all_switches),
    "performance_change_verdict": verdict_a if pct_rows else None,
    "style_similarity": style_similarity,
    "team_ability_ppg": {"before": old_team_ppg, "after": new_team_ppg},
    "league_quality_proxy": {"before": old_league_quality, "after": new_league_quality},
    "same_role": same_position,
    "destination_percentile": (
        {"metric": label, "value": percentile}
        if percentile is not None and pd.notna(player_value) else None
    ),
    "data_confidence": overall_conf_word,
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h1.json", "w") as f:
    json.dump(h1_verdict_record, f, indent=2, default=str)