import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
from datetime import datetime, timezone

# Defensive: the statistical section below needs these three packages.
# If any are missing on the deployed environment (this is exactly what
# crashed an earlier version — ModuleNotFoundError on sklearn), the
# peer-comparison charts still work fully; the statistical section just
# shows a clear message instead of crashing the page.
try:
    from scipy import stats
    import statsmodels.formula.api as smf
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    HAS_ADVANCED_LIBS = True
    MISSING_LIB_ERROR = None
except ImportError as e:
    HAS_ADVANCED_LIBS = False
    MISSING_LIB_ERROR = str(e)

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Age Optimization", layout="wide")
st.title("AGE OPTIMIZATION")

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
# Sidebar – full player roster, with a move/data indicator per player
# -------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name FROM lineups ORDER BY player_name
""").df()
if players.empty:
    st.error("No players found in lineups.parquet.")
    st.stop()

matched_ids = con.execute("""
    SELECT DISTINCT x.statsbomb_player_id AS player_id
    FROM catapult c JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id IS NOT NULL
""").df()["player_id"]
players["has_data"] = players["player_id"].isin(matched_ids)
players["display_label"] = players["player_name"] + players["has_data"].map({True: " 🟢", False: " 🔴"})

selected_label = st.sidebar.selectbox("Select Player", players["display_label"])
st.sidebar.caption("🟢 : has matched Catapult data · 🔴 : no matched data (can't be analyzed here)")

matched = players.loc[players["display_label"] == selected_label]
if matched.empty:
    st.error("Selected player not found.")
    st.stop()
player_id = int(matched["player_id"].iloc[0])
player_name = matched["player_name"].iloc[0]

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
# Fixed-width age buckets (5-year gap)
# -------------------------------
AGE_BANDS = [15, 23, 28, 33, 100]
AGE_BAND_LABELS = ["≤22", "23-27", "28-32", "33+"]
sessions["age_bucket"] = pd.cut(sessions["age"], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False)

DOMAINS = {
    "Speed": "v_max",
    "Endurance": "pl_sum",
    "Explosiveness": "a_sum",
}
METRIC_DEFINITIONS = {
    "Speed": (
        "Based on `v_max` — inferred from Catapult naming conventions as "
        "a player's maximum recorded speed per session, not yet "
        "confirmed against official documentation."
    ),
    "Endurance": (
        "Based on `pl_sum` — inferred as a cumulative player-load figure "
        "per session (summed from GPS/accelerometer data), not yet "
        "confirmed against official documentation."
    ),
    "Explosiveness": (
        "Based on `a_sum` — inferred as a cumulative high-intensity "
        "acceleration figure per session, not yet confirmed against "
        "official documentation."
    ),
}

# -------------------------------
# Selected player's own age (as of their most recent session)
# -------------------------------
player_sessions = sessions[sessions["player_id"] == player_id]
if player_sessions.empty:
    st.info(
        f"{player_name} has no Catapult sessions matched via the identity "
        f"crosswalk — the charts below still work, but this player can't "
        f"be highlighted on them."
    )
    player_current_age = None
    player_bucket = None
else:
    player_current_age = player_sessions["age"].max()
    player_bucket = pd.cut([player_current_age], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False)[0]
    st.write(f"**{player_name}'s age (most recent session):** {player_current_age:.1f} "
             f"— falls in the **{player_bucket}** bucket")

has_position = "primary_position" in con.execute("DESCRIBE lineups").df()["column_name"].values
if has_position:
    pos_df = con.execute("""
        SELECT player_id, primary_position, COUNT(*) AS n
        FROM lineups WHERE primary_position IS NOT NULL
        GROUP BY player_id, primary_position
    """).df()
    modal_position = (
        pos_df.sort_values("n", ascending=False)
        .drop_duplicates(subset=["player_id"])
        .set_index("player_id")["primary_position"]
    )
    sessions["position"] = sessions["player_id"].map(modal_position)
else:
    sessions["position"] = "ALL"  # single group = league-wide z-score, not position-stratified

if not HAS_ADVANCED_LIBS:
    st.error(
        f"The statistical analysis further below needs `scipy`, "
        f"`statsmodels`, and `scikit-learn`, which aren't available in "
        f"this deployment right now (`{MISSING_LIB_ERROR}`). The "
        f"peer-comparison charts for each metric still work fully. To "
        f"fix this: confirm `scipy`, `statsmodels`, and `scikit-learn` "
        f"are in requirements.txt on GitHub (not just locally), then "
        f"reboot/redeploy the app."
    )

method_b_results = {}

# ===========================================================
# ONE CONSOLIDATED SECTION PER METRIC — peer-comparison chart +
# statistical analysis, combined under a single heading (previously
# split across two separate page sections for the same metric).
# ===========================================================
for domain_name, metric_col in DOMAINS.items():
    st.markdown("---")
    st.subheader(domain_name)

    with st.expander("ℹ️ What does this show and how is it calculated?"):
        st.markdown(METRIC_DEFINITIONS[domain_name])
        st.markdown(
            "**Peer comparison chart:** each dot is one player's average "
            f"{domain_name.lower()} value across their own recorded "
            "sessions, among players in the same age bucket as "
            f"{player_name}. The diamond marks {player_name}'s own "
            "average. Percentile = the share of those peers whose value "
            "was lower, × 100."
        )
        st.markdown(
            "**Peak age (statistical panel):** players are split into "
            "groups by k-means clustering on their z-scored session "
            "values (the group count that best separates the data, by "
            "silhouette score, is used). Peak age is the average age of "
            "whichever group has the higher average z-score. ANOVA "
            "p-value and effect size (η²) describe how much that "
            "grouping explains variation in the metric — note that "
            "because the groups are formed FROM the same z-score being "
            "tested, a low p-value/large effect size here partly "
            "reflects how the split was built, not necessarily a "
            "genuine age effect on its own. The mixed-effects model "
            "(age bucket + position, with each player's own baseline "
            "accounted for) is a more independent check of the same "
            "question."
        )

    dom_data_all = sessions.dropna(subset=[metric_col])
    if dom_data_all.empty:
        st.info(f"No {domain_name.lower()} data available.")
        continue

    # -----------------------------------------------------------
    # Peer comparison: this player vs. others in the same age bucket
    # (replaces the earlier single combined "% of peak bucket" bar
    # chart — a distribution + percentile view, matching the
    # player-vs-peers approach used elsewhere in this project).
    # -----------------------------------------------------------
    player_avg_by_player = dom_data_all.groupby("player_id")[metric_col].mean().reset_index()
    latest_bucket_by_player = (
        dom_data_all.sort_values("date").groupby("player_id")["age_bucket"].last()
    )
    player_avg_by_player["age_bucket"] = player_avg_by_player["player_id"].map(latest_bucket_by_player)

    if player_bucket is not None:
        peer_group = player_avg_by_player[player_avg_by_player["age_bucket"] == player_bucket]
        peer_group_label = f"the {player_bucket} age bucket"
    else:
        peer_group = player_avg_by_player
        peer_group_label = "all tracked players (age bucket unavailable for this player)"

    if len(peer_group) < 5:
        st.info(f"Not enough players in {peer_group_label} to build a distribution for {domain_name}.")
    else:
        dist_fig = go.Figure()
        dist_fig.add_trace(go.Box(
            x=peer_group[metric_col], name=str(player_bucket) if player_bucket is not None else "All players",
            boxpoints="all", jitter=0.6, pointpos=0,
            marker_color="lightgray", line_color="lightgray", fillcolor="rgba(0,0,0,0)",
        ))

        player_row = player_avg_by_player[player_avg_by_player["player_id"] == player_id]
        percentile = None
        if not player_row.empty:
            player_value = player_row[metric_col].iloc[0]
            dist_fig.add_trace(go.Scatter(
                x=[player_value], y=[str(player_bucket) if player_bucket is not None else "All players"],
                mode="markers", marker=dict(size=16, color="crimson", symbol="diamond"),
                name=player_name,
            ))
            percentile = float((peer_group[metric_col] < player_value).mean() * 100)

        dist_fig.update_layout(
            title=f"{domain_name} vs. {peer_group_label}",
            xaxis_title=domain_name, height=220, showlegend=True,
        )
        st.plotly_chart(dist_fig, use_container_width=True)

        if percentile is not None:
            st.metric(f"{domain_name} percentile", f"{percentile:.0f}th percentile")
            if percentile >= 75:
                interp = f"{player_name} is near the top of {peer_group_label} for {domain_name.lower()}."
            elif percentile >= 40:
                interp = f"{player_name} sits around the middle of {peer_group_label} for {domain_name.lower()}."
            else:
                interp = f"{player_name} is in the lower portion of {peer_group_label} for {domain_name.lower()}."
            st.caption(interp)
        else:
            st.info(f"{player_name} has no {domain_name.lower()} data to compare against peers.")

    # -----------------------------------------------------------
    # Statistical analysis
    # -----------------------------------------------------------
    if not HAS_ADVANCED_LIBS:
        continue

    dom_data = sessions.dropna(subset=[metric_col, "position"]).copy()
    if dom_data.empty:
        continue

    dom_data["z"] = dom_data.groupby("position")[metric_col].transform(
        lambda s: (s - s.mean()) / s.std() if s.std() > 0 else 0
    )
    dom_data = dom_data[dom_data["z"].abs() < 3]  # exclude extreme outliers

    if len(dom_data) < 30 or dom_data["player_id"].nunique() < 10:
        st.warning(f"Not enough data for {domain_name} to run the statistical analysis reliably.")
        continue

    try:
        mlm = smf.mixedlm(
            "z ~ C(age_bucket) + C(position)", data=dom_data, groups=dom_data["player_id"]
        ).fit()
    except Exception as e:
        mlm = None
        st.info(f"Mixed-effects model could not be fit: {e}")

    X = dom_data[["z"]].values
    sil_scores = {}
    for k in [2, 3, 4]:
        if len(dom_data) > k:
            labels_k = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
            if len(set(labels_k)) > 1:
                sil_scores[k] = silhouette_score(X, labels_k)
    best_k = max(sil_scores, key=sil_scores.get) if sil_scores else 3

    kmeans = KMeans(n_clusters=best_k, n_init=10, random_state=0)
    dom_data["cluster"] = kmeans.fit_predict(X)

    cluster_stats = dom_data.groupby("cluster").agg(
        mean_age=("age", "mean"),
        age_ci=("age", lambda s: 1.96 * s.std() / np.sqrt(len(s)) if len(s) > 1 else 0),
        mean_z=("z", "mean"),
        n=("z", "count"),
    ).sort_values("mean_z", ascending=False)

    peak_cluster = cluster_stats.index[0]
    peak_age_b = cluster_stats.loc[peak_cluster, "mean_age"]
    peak_ci = cluster_stats.loc[peak_cluster, "age_ci"]

    groups_for_anova = [dom_data[dom_data["cluster"] == c]["z"].values for c in cluster_stats.index]
    f_stat, anova_p = stats.f_oneway(*groups_for_anova)
    grand_mean = dom_data["z"].mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups_for_anova)
    ss_total = sum((dom_data["z"] - grand_mean) ** 2)
    eta_sq = ss_between / ss_total if ss_total > 0 else 0

    method_b_results[domain_name] = {
        "peak_age": float(peak_age_b),
        "peak_age_ci": float(peak_ci),
        "n_clusters": int(best_k),
        "anova_p_value": float(anova_p),
        "eta_squared": float(eta_sq),
    }

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Peak age (higher-performing group)", f"{peak_age_b:.1f} ± {peak_ci:.1f}",
        help="Average age of the cluster with the higher average z-score, ± its 95% confidence interval.",
    )
    c2.metric(
        "ANOVA p-value", f"{anova_p:.4f}",
        help="Tests whether the two clusters' z-scores genuinely differ. See the caveat above about circularity.",
    )
    c3.metric(
        "Effect size (η²)", f"{eta_sq:.3f}",
        help="Share of total z-score variation explained by the cluster split (0-1). Same caveat applies.",
    )

    if mlm is not None:
        # WHAT THIS IS: a mixed-effects regression predicting each
        # session's z-score from its age bucket and position, while
        # giving every player their own baseline (random intercept) so
        # a player with many sessions doesn't dominate the estimate.
        # It's the more trustworthy of the two statistical checks on
        # this page — unlike the clustering above, its groups (age
        # buckets) are defined independently of the z-score being
        # tested, so it doesn't have that circularity problem. The raw
        # statsmodels output is a dense table meant for a statistician,
        # not a dashboard reader — this pulls out just the age-bucket
        # rows and states them in plain language instead.
        age_effect_rows = []
        for idx in mlm.params.index:
            if idx.startswith("C(age_bucket)"):
                bucket_label = idx.split("T.")[-1].rstrip("]")
                coef = mlm.params[idx]
                p = mlm.pvalues[idx]
                age_effect_rows.append({
                    "Age bucket": bucket_label,
                    "Effect vs. ≤22 baseline": round(float(coef), 3),
                    "p-value": round(float(p), 4),
                    "Significant?": "Yes" if p < 0.05 else "No",
                })

        if age_effect_rows:
            st.markdown("**Age effect, independent check (mixed-effects model):**")
            st.caption(
                "Compares each age bucket's average z-score to the ≤22 "
                "baseline, holding position constant and accounting for "
                "each player's own baseline. This is a more independent "
                "test of an age effect than the clustering/ANOVA above."
            )
            st.dataframe(pd.DataFrame(age_effect_rows), use_container_width=True, hide_index=True)

    with st.expander(f"ℹ️ What does the {domain_name.lower()} age-vs-z-score chart show?"):
        st.markdown(
            f"**What each dot is:** every gray/blue dot is ONE training "
            f"session (not one player) — the session's age (x-axis) "
            f"plotted against its z-scored {domain_name.lower()} value "
            f"(y-axis). A single player contributes many dots, one per "
            f"session."
        )
        st.markdown(
            "**What the colors mean:** sessions are split into groups "
            "by k-means clustering on the z-score alone (age isn't "
            "given to the clustering step) — each color is one such "
            "group, labeled in the legend by that group's own average "
            "age."
        )
        st.markdown(
            f"**The gold dots:** {player_name}'s own individual "
            f"sessions, shown only if they have matched data for this "
            f"metric — drawn on top of the population so you can see "
            f"where they personally fall."
        )
        st.markdown(
            "**How peak age is calculated:** whichever cluster has the "
            "higher average z-score is treated as the 'higher-"
            "performing' group. Peak age is simply that group's "
            "average age."
        )
        st.markdown(
            "**The two kinds of vertical line:** a **gray dotted line** "
            "is drawn at EVERY cluster's own average age (one per "
            "cluster/color). The **red dashed line** marks the peak "
            "cluster's average age specifically — since that's also "
            "one of the cluster mean ages, the red line always lands "
            "exactly on top of one of the gray lines."
        )

    fig_b = go.Figure()
    for c in cluster_stats.index:
        cluster_pts = dom_data[dom_data["cluster"] == c]
        fig_b.add_trace(go.Scatter(
            x=cluster_pts["age"], y=cluster_pts["z"],
            mode="markers", marker=dict(size=5, opacity=0.35),
            name=f"Cluster {c} (mean age {cluster_stats.loc[c, 'mean_age']:.1f})",
        ))
        fig_b.add_vline(x=cluster_stats.loc[c, "mean_age"], line_dash="dot", line_color="gray", opacity=0.5)

    player_pts = dom_data[dom_data["player_id"] == player_id]
    if not player_pts.empty:
        fig_b.add_trace(go.Scatter(
            x=player_pts["age"], y=player_pts["z"],
            mode="markers", marker=dict(size=12, color="gold", line=dict(width=1, color="black")),
            name=f"{player_name}'s sessions",
        ))

    fig_b.add_vline(x=peak_age_b, line_dash="dash", line_color="crimson",
                     annotation_text=f"Peak: {peak_age_b:.1f}y")
    fig_b.update_layout(
        title=f"{domain_name} — age vs. z-score, clustered (gold = {player_name})",
        xaxis_title="Age", yaxis_title=f"{domain_name} z-score",
    )
    st.plotly_chart(fig_b, use_container_width=True)

    st.caption(
        f"Peak age for {domain_name.lower()} in this data is "
        f"{peak_age_b:.1f} years (±{peak_ci:.1f}), based on {best_k} "
        f"cluster(s) found in the z-scored session data. "
        + (
            f"{player_name}'s own sessions are marked in gold above."
            if not player_pts.empty else
            f"{player_name} has no sessions in this analysis to highlight."
        )
    )

# ===========================================================
# OVERALL SUMMARY
# ===========================================================
if method_b_results:
    st.markdown("---")
    st.subheader("Peak Ages by Metric")
    st.dataframe(pd.DataFrame(method_b_results).T, use_container_width=True)
    st.caption(
        "Peak age (from the clustering analysis above) for each metric, side by side."
    )

    st.markdown("---")
    st.subheader(f"Overall Peak Age Result for {player_name}")

    if player_current_age is None:
        st.info(
            f"{player_name} has no matched Catapult sessions, so their "
            f"own age can't be compared against these peak ages."
        )
    else:
        st.write(f"**{player_name}'s current age:** {player_current_age:.1f}")
        for domain_name, res in method_b_results.items():
            peak_age = res["peak_age"]
            distance = abs(player_current_age - peak_age)
            if distance <= 1:
                dot, status = "🟢", "at/near peak age"
            elif distance <= 3:
                dot, status = "🟡", "approaching or past peak age"
            else:
                dot, status = "🔴", "well before or after peak age"
            st.write(
                f"{dot} **{domain_name}** — peak age {peak_age:.1f}y, "
                f"{status} ({distance:.1f} years from their own age)"
            )

        st.caption(
            "🟢 = within 1 year of peak age · 🟡 = within 1–3 years · "
            "🔴 = more than 3 years away. Based on the peak ages computed "
            "above for each metric — the same clustering caveat noted "
            "in each metric's own explanation applies here too."
        )

    verdict_record = {
        "hypothesis": "H3 — Age Optimization",
        "method_b": {
            "domains": method_b_results,
            "last_computed": datetime.now(timezone.utc).isoformat(),
        },
    }
    with open("verdict_h3.json", "w") as f:
        json.dump(verdict_record, f, indent=2)