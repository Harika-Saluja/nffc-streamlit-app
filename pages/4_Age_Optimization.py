import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
from datetime import datetime, timezone

# Defensive: Step 2 below needs these three packages. If any are missing
# on the deployed environment (this is exactly what crashed the previous
# version — ModuleNotFoundError on sklearn), Step 1 above still works
# fully; Step 2 just shows a clear message instead of crashing the page.
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
        "yet. The rigorous version (z-score, ROUT, mixed-effects model, "
        "clustering) is Step 2 below."
    )

# ===========================================================
# STEP 2 — Branquinho et al. (2025) methodology
# "The Aging Curve: How Age Affects Physical Performance in Elite
# Football", J. Funct. Morphol. Kinesiol. 10(4):385.
# https://doi.org/10.3390/jfmk10040385
#
# Gated behind HAS_ADVANCED_LIBS — if scipy/statsmodels/sklearn aren't
# installed on this deployment, this section shows a clear message
# instead of crashing the whole page (Step 1 above still works either way).
# ===========================================================
st.markdown("---")
st.header("Step 2 — Paper-Replicated Pipeline (Branquinho et al., 2025)")

if not HAS_ADVANCED_LIBS:
    st.error(
        f"This section needs `scipy`, `statsmodels`, and `scikit-learn`, "
        f"which aren't available in this deployment right now "
        f"(`{MISSING_LIB_ERROR}`). Step 1 above still works fully. To fix "
        f"this section: confirm `scipy`, `statsmodels`, and `scikit-learn` "
        f"are in requirements.txt on GitHub (not just locally), then "
        f"reboot/redeploy the app."
    )
else:
    st.caption(
        "Following: Branquinho, L. et al. (2025). The Aging Curve: How Age "
        "Affects Physical Performance in Elite Football. J. Funct. "
        "Morphol. Kinesiol. 10(4), 385. https://doi.org/10.3390/jfmk10040385"
    )

    has_position = "primary_position" in con.execute("DESCRIBE lineups").df()["column_name"].values
    if not has_position:
        st.warning(
            "`primary_position` not found in lineups.parquet — position-"
            "stratified z-scoring below will be skipped (uses league-wide "
            "z-scores instead of within-position, a less faithful "
            "replication of the paper's method until the dataset is "
            "rebuilt with that field)."
        )

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

    method_b_results = {}

    for domain_name, metric_col in DOMAINS.items():
        st.markdown("---")
        st.subheader(f"{domain_name} ({metric_col})")

        dom_data = sessions.dropna(subset=[metric_col, "position"]).copy()
        if dom_data.empty:
            st.info(f"No {domain_name.lower()} data available.")
            continue

        # z-score WITHIN position (or league-wide if position unavailable)
        dom_data["z"] = dom_data.groupby("position")[metric_col].transform(
            lambda s: (s - s.mean()) / s.std() if s.std() > 0 else 0
        )

        # ROUT outlier removal: exclude |z| >= 3, per the paper's stated rule
        n_before = len(dom_data)
        dom_data = dom_data[dom_data["z"].abs() < 3]
        n_removed = n_before - len(dom_data)
        st.caption(f"ROUT outlier removal: {n_removed} of {n_before} sessions excluded (|z| ≥ 3).")

        if len(dom_data) < 30 or dom_data["player_id"].nunique() < 10:
            st.warning(f"Not enough data for {domain_name} to run this pipeline reliably.")
            continue

        # mixed linear model: z ~ age_bucket + position, player random intercept
        try:
            mlm = smf.mixedlm(
                "z ~ C(age_bucket) + C(position)", data=dom_data, groups=dom_data["player_id"]
            ).fit()
            mlm_summary = mlm.summary().tables[1]
        except Exception as e:
            mlm = None
            st.info(f"Mixed linear model could not be fit: {e}")

        # hierarchical clustering (via silhouette) + k-means
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

        st.caption(
            f"Silhouette scores by k: {', '.join(f'{k}={v:.2f}' for k, v in sil_scores.items())} "
            f"— using k={best_k}."
        )

        # one-way ANOVA + eta-squared (Duncan's post-hoc not available in
        # Python's standard stats libraries — omitted here rather than
        # substituting silently; Tukey HSD is a reasonable addition if
        # this needs a formal pairwise test later)
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
        c1.metric("Peak age (best cluster)", f"{peak_age_b:.1f} ± {peak_ci:.1f}")
        c2.metric("ANOVA p-value", f"{anova_p:.4f}")
        c3.metric("Effect size (η²)", f"{eta_sq:.3f}")

        if mlm is not None:
            with st.expander("Mixed linear model summary (z ~ age_bucket + position, player random intercept)"):
                st.dataframe(mlm_summary)

        # chart: age vs z, colored by cluster, selected player highlighted
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

    if method_b_results:
        st.markdown("---")
        st.subheader("Step 2 Summary — Peak Ages by Domain")
        st.dataframe(pd.DataFrame(method_b_results).T, use_container_width=True)

        verdict_record = {
            "hypothesis": "H3 — Age Optimization",
            "method_b": {
                "citation": "Branquinho et al. (2025), J. Funct. Morphol. Kinesiol. 10(4):385",
                "domains": method_b_results,
                "last_computed": datetime.now(timezone.utc).isoformat(),
            },
        }
        with open("verdict_h3.json", "w") as f:
            json.dump(verdict_record, f, indent=2)