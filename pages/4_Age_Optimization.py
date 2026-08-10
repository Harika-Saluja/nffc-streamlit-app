import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Age Optimization", layout="wide")
st.title("Age Optimization")
st.caption(
    "Step 1: Speed, Endurance, and Explosiveness by age — using fixed "
    "5-year age buckets. No clustering/z-score/mixed-model yet — that's "
    "a later step, added once this base version is confirmed working."
)
st.warning(
    "**Scope note:** the original brief framed this as 'performance-to-cost "
    "ratio' — no wage/salary data exists anywhere in this project's bucket, "
    "so this tests performance by age only, not cost-adjusted."
)

# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')
con.execute("""
    CREATE TABLE lineups   AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE catapult  AS SELECT * FROM read_parquet('catapult.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
""")

# -------------------------------
# Sidebar – full player roster (only players with Catapult data are
# useful here, but we still show the full roster and handle the
# no-data case gracefully rather than silently filtering the list)
# -------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name FROM lineups ORDER BY player_name
""").df()
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

# -------------------------------
# Build the Catapult session table with age at each session
# -------------------------------
sessions = con.execute("""
    SELECT x.statsbomb_player_id AS player_id, c.date,
           c.v_max, c.pl_sum, c.a_sum
    FROM catapult c
    JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id IS NOT NULL
""").df()

birth_dates = con.execute("SELECT DISTINCT player_id, birth_date FROM lineups").df()

if sessions.empty:
    st.error(
        "No Catapult sessions could be matched to any player via the "
        "identity crosswalk. Nothing further on this page can be shown "
        "until that's resolved."
    )
    st.stop()

sessions["date"] = pd.to_datetime(sessions["date"])
birth_dates["birth_date"] = pd.to_datetime(birth_dates["birth_date"])
sessions = sessions.merge(birth_dates, on="player_id", how="left")
sessions["age"] = (sessions["date"] - sessions["birth_date"]).dt.days / 365.25
sessions = sessions.dropna(subset=["age"])
sessions = sessions[(sessions["age"] >= 15) & (sessions["age"] <= 45)]  # sanity bounds

if sessions.empty:
    st.warning("No sessions with valid age data after filtering.")
    st.stop()

# -------------------------------
# Fixed-width age buckets (5-year gap), following Branquinho et al. (2025)
# -------------------------------
AGE_BANDS = [15, 23, 28, 33, 100]
AGE_BAND_LABELS = ["≤22", "23-27", "28-32", "33+"]
sessions["age_bucket"] = pd.cut(sessions["age"], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False)

DOMAINS = {
    "Speed": "v_max",
    "Endurance": "pl_sum",
    "Explosiveness": "a_sum",
}

# -------------------------------
# Selected player's own age (as of their most recent session)
# -------------------------------
player_sessions = sessions[sessions["player_id"] == player_id]
if player_sessions.empty:
    st.info(
        f"{player_name} has no Catapult sessions matched via the identity "
        f"crosswalk — the population charts below still work, but this "
        f"player can't be highlighted on them."
    )
    player_current_age = None
    player_bucket = None
else:
    player_current_age = player_sessions["age"].max()
    player_bucket = pd.cut([player_current_age], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False)[0]
    st.write(f"**{player_name}'s age (most recent session):** {player_current_age:.1f} "
             f"— falls in the **{player_bucket}** bucket")

# ===========================================================
# THREE METRICS x AGE BUCKET — simple bucket means, no clustering yet
# ===========================================================
st.markdown("---")
st.header("Performance by Age Bucket")

peak_summary = []

for domain_name, metric_col in DOMAINS.items():
    st.subheader(domain_name)

    dom_data = sessions.dropna(subset=[metric_col])
    if dom_data.empty:
        st.info(f"No {domain_name.lower()} data available.")
        continue

    bucket_stats = dom_data.groupby("age_bucket", observed=True)[metric_col].agg(
        mean="mean", std="std", n="count"
    ).reindex(AGE_BAND_LABELS).dropna(subset=["mean"])

    if bucket_stats.empty:
        st.info(f"Not enough {domain_name.lower()} data across age buckets.")
        continue

    bucket_stats["ci95"] = 1.96 * bucket_stats["std"] / np.sqrt(bucket_stats["n"])
    best_bucket = bucket_stats["mean"].idxmax()
    peak_summary.append({"Domain": domain_name, "Peak Age Bucket": best_bucket,
                          "Mean Value": round(bucket_stats.loc[best_bucket, "mean"], 2)})

    bar_colors = ["gold" if b == best_bucket else "steelblue" for b in bucket_stats.index]
    bar_fig = go.Figure(go.Bar(
        x=bucket_stats.index, y=bucket_stats["mean"],
        error_y=dict(type="data", array=bucket_stats["ci95"].fillna(0)),
        marker_color=bar_colors,
        text=[f"{v:.1f} (n={n})" for v, n in zip(bucket_stats["mean"], bucket_stats["n"])],
        textposition="outside",
    ))
    if player_bucket is not None:
        bar_fig.add_annotation(
            x=str(player_bucket), y=bucket_stats.loc[player_bucket, "mean"] if player_bucket in bucket_stats.index else 0,
            text=f"← {player_name}", showarrow=True, arrowhead=2,
        )
    bar_fig.update_layout(
        title=f"{domain_name} ({metric_col}) by age bucket — gold = highest mean",
        xaxis_title="Age bucket", yaxis_title=metric_col,
    )
    st.plotly_chart(bar_fig, use_container_width=True)

    st.caption(
        "Column meanings (v_max, pl_sum, a_sum) are inferred from Catapult "
        "naming conventions, not yet confirmed against official "
        "documentation — treat as relative/comparative, not verified units."
    )

# ===========================================================
# SUMMARY TABLE
# ===========================================================
if peak_summary:
    st.markdown("---")
    st.header("Peak Age Summary")
    st.dataframe(pd.DataFrame(peak_summary), use_container_width=True, hide_index=True)
    st.caption(
        "This is a simple bucket-mean comparison — no significance testing "
        "yet (Kruskal-Wallis / Dunn's / mixed-effects clustering are "
        "planned as the next step once this base version is confirmed "
        "stable in deployment)."
    )