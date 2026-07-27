import streamlit as st
import duckdb
import json
import os
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Myth Verdict Dashboard", layout="wide")
st.title("Myth Verdict Dashboard")
st.caption(
    "Population-level verdicts are pulled from each hypothesis page's own "
    "saved results. If a hypothesis shows 'Not yet computed', visit that "
    "page first. Select a player below to see how they specifically fit "
    "into each verdict."
)

BADGE = {"SUPPORTED": "🔴", "NOT SUPPORTED": "🟢", "INCONCLUSIVE": "🟡",
         "SIGNIFICANT DIFFERENCE EXISTS": "🔴", "NO SIGNIFICANT DIFFERENCE": "🟢",
         "NOT COMPUTED": "⚪"}


def load_verdict(filename: str) -> dict | None:
    if not os.path.exists(filename):
        return None
    with open(filename) as f:
        return json.load(f)


def render_not_computed(hypothesis_name: str, page_name: str):
    st.info(
        f"**{hypothesis_name}** hasn't been computed yet. "
        f"Visit the **{page_name}** page to run its tests — the result "
        f"will then appear here automatically."
    )


def render_timestamp(record: dict):
    ts = record.get("last_computed")
    if ts:
        dt = datetime.fromisoformat(ts)
        st.caption(f"Last computed: {dt.strftime('%Y-%m-%d %H:%M UTC')}")


# -------------------------------
# Sidebar – player selector. Population verdicts above don't
# change per player, but each hypothesis gets a small "in this
# player's case" callout pulled fresh from the underlying data,
# since the saved verdict JSONs only hold population results.
# -------------------------------
con = duckdb.connect(database=':memory:')
con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE matches AS SELECT * FROM read_parquet('matches.parquet');
    CREATE TABLE events  AS SELECT * FROM read_parquet('events.parquet');
    CREATE TABLE injuries AS SELECT * FROM read_parquet('injuries.parquet');
""")

st.sidebar.title("Player Selector")
players = con.execute("""
    SELECT DISTINCT player_id, player_name FROM lineups ORDER BY player_name
""").df()
player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(f"Myth Verdict Summary for {player_name}")

# ---------------------------------------------------------
# HYPOTHESIS 1 – LEAGUE ADAPTATION
# ---------------------------------------------------------
st.subheader("Hypothesis 1: League Adaptation")

h1 = load_verdict("verdict_h1.json")
if h1 is None:
    render_not_computed("H1", "League Adaptation")
else:
    st.write(f"*Metric tested: {h1['metric']}*")
    t1, t2 = h1["test_1"], h1["test_2"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Test 1 — {t1['name']}**")
        if t1["verdict"] == "NOT COMPUTED":
            st.write("Not enough data to run this test.")
        else:
            st.metric("Verdict", f"{BADGE.get(t1['verdict'], '⚪')} {t1['verdict']}")
            st.write(f"p-value: `{t1['p_value']:.4f}`  ·  effect size: `{t1['effect_size']:+.3f}`")
    with c2:
        st.markdown(f"**Test 2 — {t2['name']}**")
        if t2["verdict"] == "NOT COMPUTED":
            st.write("Not enough data to run this test.")
        else:
            st.metric("Verdict", f"{BADGE.get(t2['verdict'], '⚪')} {t2['verdict']}")
            st.write(f"p-value: `{t2['p_value']:.4f}`  ·  coefficient: `{t2['coefficient']:+.3f}`")

    render_timestamp(h1)

# per-player context: was this player ever "new" in the dataset?
player_seasons = con.execute(f"""
    SELECT m.season, COUNT(DISTINCT l.match_id) AS matches_played
    FROM lineups l JOIN matches m ON l.match_id = m.match_id
    WHERE l.player_id = {player_id}
    GROUP BY m.season ORDER BY m.season
""").df()

if player_seasons.empty:
    st.caption(f"No season data found for {player_name}.")
else:
    debut_season = player_seasons["season"].min()
    all_seasons_in_data = con.execute("SELECT MIN(season) AS s FROM matches").df()["s"].iloc[0]
    if debut_season == all_seasons_in_data:
        st.caption(
            f"📍 **In {player_name}'s case:** their earliest tracked season is "
            f"{debut_season} — the first season in our dataset, so we can't "
            f"confirm this is genuinely their PL debut (left-censored, see "
            f"the League Adaptation page for detail)."
        )
    else:
        st.caption(
            f"📍 **In {player_name}'s case:** first tracked season is "
            f"{debut_season} — flagged as a debut season. See the League "
            f"Adaptation page, selecting this player, for their specific "
            f"before/after comparison."
        )

st.markdown("---")

# ---------------------------------------------------------
# HYPOTHESIS 2 – WORKLOAD & INJURY RISK
# ---------------------------------------------------------
st.subheader("Hypothesis 2: Workload & Injury Risk")

h2 = load_verdict("verdict_h2.json")
if h2 is None:
    render_not_computed("H2", "Workload & Injury Risk")
else:
    st.write(
        f"*Metric tested: {h2['metric']}  ·  "
        f"window: {h2['window_days']}d  ·  follow-up: {h2['follow_days']}d*"
    )
    t1, t2 = h2["test_1"], h2["test_2"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Test 1 — {t1['name']}**")
        st.metric("Verdict", f"{BADGE.get(t1['verdict'], '⚪')} {t1['verdict']}")
        st.write(f"p-value: `{t1['p_value']:.4f}`  ·  effect size: `{t1['effect_size']:+.3f}`")
    with c2:
        st.markdown(f"**Test 2 — {t2['name']}**")
        st.metric("Verdict", f"{BADGE.get(t2['verdict'], '⚪')} {t2['verdict']}")
        sig = t2["significant_predictors"]
        st.write(f"Significant predictors: {', '.join(sig) if sig else 'none'}")
        st.json(t2["odds_ratios"], expanded=False)

    render_timestamp(h2)

# per-player context: injury history flag
player_injuries = con.execute(f"""
    SELECT COUNT(*) AS n_injuries, COALESCE(SUM(days_missed), 0) AS total_days
    FROM injuries WHERE statsbomb_id = {player_id}
""").df()
n_inj = int(player_injuries["n_injuries"].iloc[0])

if n_inj == 0:
    st.caption(f"📍 **In {player_name}'s case:** no injury records in our dataset.")
else:
    total_days = int(player_injuries["total_days"].iloc[0])
    st.caption(
        f"📍 **In {player_name}'s case:** {n_inj} injury record(s), "
        f"{total_days} total days missed. See the Workload & Injury Risk "
        f"page, selecting this player, for their specific load trend "
        f"around each injury."
    )

st.markdown("---")

# ---------------------------------------------------------
# HYPOTHESIS 3 – AGE OPTIMIZATION
# ---------------------------------------------------------
st.subheader("Hypothesis 3: Age Optimization")

h3 = load_verdict("verdict_h3.json")
if h3 is None:
    render_not_computed("H3", "Age Optimization")
else:
    st.write(f"*Metric tested: {h3['metric']}*")
    t1, t2 = h3["test_1"], h3["test_2"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Test 1 — {t1['name']}**")
        if t1["verdict"] == "NOT COMPUTED":
            st.write("Not enough data to run this test.")
        else:
            st.metric("Verdict", f"{BADGE.get(t1['verdict'], '⚪')} {t1['verdict']}")
            st.write(
                f"Kruskal-Wallis p-value: `{t1['kruskal_wallis_p_value']:.4f}`  ·  "
                f"Best-performing bucket: **{t1['best_bucket']}**"
            )
    with c2:
        st.markdown(f"**Test 2 — {t2['name']}**")
        st.metric(
            "Estimated peak age",
            f"{t2['estimated_peak_age']:.1f}" if t2["estimated_peak_age"] else "—",
        )
        st.write(
            f"Shape: {t2['shape']}  ·  "
            f"Falls in 24-27 range: {'Yes' if t2['falls_in_24_27_range'] else 'No'}"
        )

    render_timestamp(h3)

    # per-player context: which bucket does this player currently fall into?
    player_age_row = con.execute(f"""
        SELECT MAX(m.match_date) AS latest_match, l.birth_date
        FROM lineups l JOIN matches m ON l.match_id = m.match_id
        WHERE l.player_id = {player_id}
        GROUP BY l.birth_date
    """).df()

    if not player_age_row.empty and pd.notna(player_age_row["birth_date"].iloc[0]):
        latest = pd.to_datetime(player_age_row["latest_match"].iloc[0])
        birth = pd.to_datetime(player_age_row["birth_date"].iloc[0])
        current_age = (latest - birth).days / 365.25

        BUCKET_EDGES = [15, 21, 24, 28, 32, 45]
        BUCKET_LABELS = ["≤20", "21-23", "24-27", "28-31", "32+"]
        player_bucket = pd.cut([current_age], bins=BUCKET_EDGES, labels=BUCKET_LABELS, right=False)[0]

        best_bucket = t1.get("best_bucket")
        is_best = player_bucket == best_bucket
        bucket_note = (
            "This is the population's best-performing bucket. ✅" if is_best
            else f"The best-performing bucket is {best_bucket}, not this one."
        )

        st.caption(
            f"📍 **In {player_name}'s case:** age {current_age:.1f} at their most "
            f"recent match — falls in the **{player_bucket}** bucket. {bucket_note}"
        )
    else:
        st.caption(f"No age data available for {player_name}.")

st.markdown("---")

# ---------------------------------------------------------
# HYPOTHESIS 4 – SQUAD BALANCE (not yet built)
# ---------------------------------------------------------
st.subheader("Hypothesis 4: Squad Balance")
st.info(
    "H4 (Squad Balance) hasn't been built yet — pending the position-data "
    "decision (rebuild lineups.parquet to add position, or age-only scope)."
)

st.markdown("---")

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.caption(
    "Population verdicts are pulled live from each hypothesis page's own "
    "saved results — refresh after revisiting H1/H2/H3 to see updated "
    "numbers if you've changed any sliders there. Per-player context "
    "(📍 callouts) is computed fresh on this page for whichever player "
    "is selected in the sidebar."
)