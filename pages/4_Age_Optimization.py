import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
import scikit_posthocs as sp
import statsmodels.formula.api as smf
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import json
from datetime import datetime, timezone

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Age Optimization", layout="wide")
st.title("Age Optimization")
st.caption(
    "H3: Players in a specific age range provide the best performance "
    "output, compared to younger and older players."
)
st.warning(
    "**Scope note:** the original brief framed this as "
    "'performance-to-cost ratio' — no wage/salary data exists anywhere "
    "in the bucket, so this tests performance by age only. **We are not "
    "assuming 24-27 is the peak** — every age bucket is compared against "
    "every other bucket, and the best-performing bucket is whichever one "
    "the data actually shows, not a bucket chosen in advance."
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
# Build player-match table with age at match and per-90 output
# -------------------------------
raw = con.execute("""
    SELECT
        l.player_id, l.player_name, l.match_id, l.minutes_played, l.birth_date,
        m.match_date,
        COALESCE(e.xg_sum, 0) AS xg_sum,
        e.pass_success_mean,
        COALESCE(e.event_count, 0) AS event_count
    FROM lineups l
    JOIN matches m ON l.match_id = m.match_id
    LEFT JOIN events e ON e.match_id = l.match_id AND e.player_id = l.player_id
    WHERE l.minutes_played >= 45
""").df()

raw["match_date"] = pd.to_datetime(raw["match_date"])
raw["birth_date"] = pd.to_datetime(raw["birth_date"])
raw["age_at_match"] = (raw["match_date"] - raw["birth_date"]).dt.days / 365.25
raw["xg_90"] = raw["xg_sum"] / raw["minutes_played"] * 90
raw["events_90"] = raw["event_count"] / raw["minutes_played"] * 90

# -------------------------------
# Sidebar – full player roster
# -------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name FROM lineups ORDER BY player_name
""").df()
player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(player_name)

raw = raw.dropna(subset=["age_at_match"])
raw = raw[(raw["age_at_match"] >= 15) & (raw["age_at_match"] <= 45)]

# -------------------------------
# Metric selector
# -------------------------------
metric_choice = st.radio(
    "Metric:", ["xG per 90", "Pass Success %", "Events per 90"], horizontal=True
)
metric_map = {
    "xG per 90": ("xg_90", "xG / 90"),
    "Pass Success %": ("pass_success_mean", "Pass success (mean probability)"),
    "Events per 90": ("events_90", "Events / 90"),
}
col, label = metric_map[metric_choice]
data = raw.dropna(subset=[col])

# -------------------------------
# Age buckets
# -------------------------------
BUCKET_EDGES = [15, 21, 24, 28, 32, 45]
BUCKET_LABELS = ["≤20", "21-23", "24-27", "28-31", "32+"]
data["age_bucket"] = pd.cut(data["age_at_match"], bins=BUCKET_EDGES, labels=BUCKET_LABELS, right=False)

# ===========================================================
# TEST 1 — Kruskal-Wallis + FULL pairwise Dunn's post-hoc
# ===========================================================
st.markdown("---")
st.header("Method A, Test 1 — Age Bucket Comparison (Kruskal-Wallis + Dunn's Post-Hoc)")

bucket_groups = [data[data["age_bucket"] == b][col].dropna() for b in BUCKET_LABELS]
bucket_groups_valid = [(lbl, g) for lbl, g in zip(BUCKET_LABELS, bucket_groups) if len(g) >= 10]

best_bucket = None
kw_pval = None

if len(bucket_groups_valid) < 3:
    st.warning("Not enough data across enough buckets to run this test reliably.")
else:
    valid_labels = [lbl for lbl, _ in bucket_groups_valid]
    valid_groups = [g for _, g in bucket_groups_valid]

    h_stat, kw_pval = stats.kruskal(*valid_groups)

    bucket_stats = data[data["age_bucket"].isin(valid_labels)].groupby("age_bucket", observed=True)[col].agg(
        mean="mean", std="std", n="count"
    ).reindex(valid_labels)
    bucket_stats["ci95"] = 1.96 * bucket_stats["std"] / np.sqrt(bucket_stats["n"])

    best_bucket = bucket_stats["mean"].idxmax()

    bar_colors = ["gold" if b == best_bucket else "steelblue" for b in bucket_stats.index]
    bar_fig = go.Figure(go.Bar(
        x=bucket_stats.index, y=bucket_stats["mean"],
        error_y=dict(type="data", array=bucket_stats["ci95"]),
        marker_color=bar_colors,
        text=[f"{v:.3f}" for v in bucket_stats["mean"]],
        textposition="outside",
    ))
    bar_fig.update_layout(
        title=f"{label} by age bucket (gold = highest mean) — Kruskal-Wallis p={kw_pval:.4f}",
        xaxis_title="Age bucket", yaxis_title=label,
    )
    st.plotly_chart(bar_fig, use_container_width=True)

    kw_verdict = "SIGNIFICANT DIFFERENCE EXISTS" if kw_pval < 0.05 else "NO SIGNIFICANT DIFFERENCE"
    kw_badge = "🔴" if kw_pval < 0.05 else "🟢"
    c1, c2, c3 = st.columns(3)
    c1.metric("Kruskal-Wallis p-value", f"{kw_pval:.4f}")
    c2.metric("Best-performing bucket (by mean)", best_bucket)
    c3.metric("Omnibus verdict", f"{kw_badge} {kw_verdict}")

    st.caption(
        "Kruskal-Wallis only tells us SOME bucket differs from SOME other "
        "bucket — Dunn's test below checks every bucket against every "
        "other bucket individually, Holm-corrected for multiple comparisons."
    )

    st.subheader("Pairwise Comparison — Every Bucket vs. Every Other Bucket")

    valid_data = data[data["age_bucket"].isin(valid_labels)].copy()
    dunn_result = sp.posthoc_dunn(
        valid_data, val_col=col, group_col="age_bucket", p_adjust="holm"
    ).reindex(index=valid_labels, columns=valid_labels)

    heat_fig = go.Figure(go.Heatmap(
        z=dunn_result.values, x=dunn_result.columns, y=dunn_result.index,
        colorscale="RdYlGn_r", zmin=0, zmax=1,
        text=[[f"{v:.3f}" for v in row] for row in dunn_result.values],
        texttemplate="%{text}",
        colorbar=dict(title="p-value"),
    ))
    heat_fig.update_layout(
        title="Dunn's post-hoc p-values (Holm-corrected) — red/orange = significant (p<0.05)",
    )
    st.plotly_chart(heat_fig, use_container_width=True)

    if best_bucket in dunn_result.index:
        sig_vs_best = dunn_result.loc[best_bucket]
        beats = [b for b in valid_labels if b != best_bucket and sig_vs_best[b] < 0.05]
        not_sig = [b for b in valid_labels if b != best_bucket and sig_vs_best[b] >= 0.05]

        if beats:
            st.success(f"**{best_bucket}** significantly outperforms: {', '.join(beats)} (p < 0.05).")
        if not_sig:
            st.info(f"**{best_bucket}** is NOT significantly different from: {', '.join(not_sig)}.")

# ===========================================================
# TEST 2 — Quadratic regression on continuous age
# ===========================================================
st.markdown("---")
st.header("Method A, Test 2 — Peak Age (Quadratic Regression)")

reg_data = data.dropna(subset=["age_at_match", col])
X = reg_data["age_at_match"].values
y = reg_data[col].values

coeffs = np.polyfit(X, y, deg=2)
c_, b_, a_ = coeffs
poly = np.poly1d(coeffs)

peak_age = -b_ / (2 * c_) if c_ != 0 else None

age_range = np.linspace(X.min(), X.max(), 200)
fitted_curve = poly(age_range)

scatter_fig = go.Figure()
scatter_fig.add_trace(go.Scatter(
    x=X, y=y, mode="markers", marker=dict(size=4, color="steelblue", opacity=0.2),
    name="All player-matches",
))
scatter_fig.add_trace(go.Scatter(
    x=age_range, y=fitted_curve, mode="lines",
    line=dict(color="crimson", width=3), name="Fitted quadratic curve",
))

player_points = reg_data[reg_data["player_id"] == player_id]
if not player_points.empty:
    scatter_fig.add_trace(go.Scatter(
        x=player_points["age_at_match"], y=player_points[col],
        mode="markers", marker=dict(size=10, color="gold", line=dict(width=1, color="black")),
        name=f"{player_name}'s matches",
    ))

if peak_age is not None and X.min() <= peak_age <= X.max():
    scatter_fig.add_vline(
        x=peak_age, line_dash="dash", line_color="gray",
        annotation_text=f"Model peak: age {peak_age:.1f}",
    )
scatter_fig.update_layout(
    title=f"{label} vs. age — fitted peak from the data (gold = {player_name})",
    xaxis_title="Age at match", yaxis_title=label,
)
st.plotly_chart(scatter_fig, use_container_width=True)

if player_points.empty:
    st.caption(f"{player_name} has no eligible matches (45+ minutes) for this metric.")
else:
    current_age = player_points["age_at_match"].max()
    st.caption(
        f"{player_name}'s most recent tracked age in this data: {current_age:.1f}. "
        f"Their matches are highlighted in gold above."
    )

is_downward_parabola = c_ < 0
in_2427_range = peak_age is not None and 24 <= peak_age <= 27

c1, c2, c3 = st.columns(3)
c1.metric("Estimated peak age", f"{peak_age:.1f}" if peak_age is not None else "—")
c2.metric("Shape", "Peaks then declines" if is_downward_parabola else "No clear peak")
c3.metric("Falls in 24-27 range?", "Yes" if in_2427_range else "No")

st.caption(
    "This model doesn't yet account for repeated observations from the "
    "same player — a mixed-effects quadratic model would control for that."
)

verdict_record = {
    "hypothesis": "H3 — Age Optimization",
    "metric": label,
    "test_1": {
        "name": "Kruskal-Wallis + Dunn's Post-Hoc (Age Buckets)",
        "kruskal_wallis_p_value": float(kw_pval) if kw_pval is not None else None,
        "best_bucket": best_bucket,
        "verdict": (
            "SIGNIFICANT DIFFERENCE EXISTS" if kw_pval is not None and kw_pval < 0.05
            else "NO SIGNIFICANT DIFFERENCE" if kw_pval is not None
            else "NOT COMPUTED"
        ),
    },
    "test_2": {
        "name": "Quadratic Regression (Peak Age)",
        "estimated_peak_age": float(peak_age) if peak_age is not None else None,
        "falls_in_24_27_range": bool(in_2427_range),
        "shape": "Peaks then declines" if is_downward_parabola else "No clear peak",
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h3.json", "w") as f:
    json.dump(verdict_record, f, indent=2)

# ===========================================================
# METHOD B — replicating Branquinho et al. (2025), "The Aging
# Curve: How Age Affects Physical Performance in Elite Football",
# J. Funct. Morphol. Kinesiol. 10(4):385.
# https://doi.org/10.3390/jfmk10040385
#
# Deviations from the paper (stated upfront, not hidden):
#   - All three domains sourced from Catapult alone (speed=v_max,
#     endurance=pl_sum, explosiveness=a_sum) — no SecondSpectrum
#     tracking, since there's no game-ID crosswalk between
#     opta_match_id and StatsBomb match_id in this project.
#   - Position is each player's career-most-common primary_position,
#     not per-session (Catapult sessions aren't tied to a match).
#   - ROUT implemented as the paper's own stated z>=3 threshold, not
#     the full GraphPad regression-residual algorithm.
#   - Duncan's post-hoc substituted with Tukey HSD (not available in
#     Python's standard stats libraries).
#   - Coach omitted as covariate (no coach data anywhere).
# ===========================================================
st.markdown("---")
st.header("Method B — Paper-Replicated Pipeline (Branquinho et al., 2025)")
st.caption(
    "Following the exact terminology and age bands from: Branquinho, L. et al. "
    "(2025). The Aging Curve: How Age Affects Physical Performance in Elite "
    "Football. Journal of Functional Morphology and Kinesiology, 10(4), 385. "
    "https://doi.org/10.3390/jfmk10040385"
)
st.warning(
    "**Deviations from the paper** (see code comments for full detail): all "
    "three domains sourced from Catapult only; position is career-most-"
    "common, not per-session; ROUT = paper's own stated z≥3 rule; Duncan's "
    "post-hoc substituted with Tukey HSD; coach omitted (no data)."
)

AGE_BANDS = [18, 23, 28, 33, 100]
AGE_BAND_LABELS = ["18-22", "23-27", "28-32", "32+"]

con.execute("""
    CREATE TABLE catapult_b  AS SELECT * FROM read_parquet('catapult.parquet');
    CREATE TABLE crosswalk_b AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
""")

if "primary_position" in con.execute("DESCRIBE lineups").df()["column_name"].values:
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
else:
    modal_position = pd.Series(dtype=str)
    st.error(
        "`lineups.parquet` has no `primary_position` column — rebuild "
        "lineups with the position-capture step before Method B will work."
    )

catapult_sessions = con.execute("""
    SELECT x.statsbomb_player_id AS player_id, c.date,
           c.v_max, c.pl_sum, c.a_sum
    FROM catapult_b c
    JOIN crosswalk_b x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id IS NOT NULL
""").df()
catapult_sessions["date"] = pd.to_datetime(catapult_sessions["date"])

birth_dates = con.execute("SELECT DISTINCT player_id, birth_date FROM lineups").df()
birth_dates["birth_date"] = pd.to_datetime(birth_dates["birth_date"])
catapult_sessions = catapult_sessions.merge(birth_dates, on="player_id", how="left")
catapult_sessions["age"] = (
    (catapult_sessions["date"] - catapult_sessions["birth_date"]).dt.days / 365.25
)
catapult_sessions["age_band"] = pd.cut(
    catapult_sessions["age"], bins=AGE_BANDS, labels=AGE_BAND_LABELS, right=False
)
catapult_sessions["position"] = catapult_sessions["player_id"].map(modal_position)
catapult_sessions = catapult_sessions.dropna(subset=["age", "position"])

DOMAINS = {"Speed": "v_max", "Endurance": "pl_sum", "Explosiveness": "a_sum"}
method_b_results = {}

for domain_name, metric_col in DOMAINS.items():
    st.markdown("---")
    st.subheader(f"{domain_name} ({metric_col})")

    dom_data = catapult_sessions.dropna(subset=[metric_col]).copy()

    dom_data["z"] = dom_data.groupby("position")[metric_col].transform(
        lambda s: (s - s.mean()) / s.std() if s.std() > 0 else 0
    )

    n_before = len(dom_data)
    dom_data = dom_data[dom_data["z"].abs() < 3]
    n_removed = n_before - len(dom_data)
    st.caption(f"ROUT outlier removal: {n_removed} of {n_before} sessions excluded (|z| ≥ 3).")

    if len(dom_data) < 30 or dom_data["player_id"].nunique() < 10:
        st.warning(f"Not enough data for {domain_name} to run this pipeline reliably.")
        continue

    try:
        mlm = smf.mixedlm(
            "z ~ C(age_band) + C(position)", data=dom_data, groups=dom_data["player_id"]
        ).fit()
        mlm_summary = mlm.summary().tables[1]
    except Exception as e:
        mlm = None
        st.info(f"Mixed linear model could not be fit: {e}")

    X_ = dom_data[["z"]].values
    sil_scores = {}
    for k in [2, 3, 4]:
        if len(dom_data) > k:
            labels_k = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X_)
            if len(set(labels_k)) > 1:
                sil_scores[k] = silhouette_score(X_, labels_k)
    best_k = max(sil_scores, key=sil_scores.get) if sil_scores else 3

    kmeans = KMeans(n_clusters=best_k, n_init=10, random_state=0)
    dom_data["cluster"] = kmeans.fit_predict(X_)

    cluster_stats = dom_data.groupby("cluster").agg(
        mean_age=("age", "mean"),
        age_ci=("age", lambda s: 1.96 * s.std() / np.sqrt(len(s))),
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

    groups_for_anova = [dom_data[dom_data["cluster"] == c]["z"].values for c in cluster_stats.index]
    f_stat, anova_p = stats.f_oneway(*groups_for_anova)
    grand_mean = dom_data["z"].mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups_for_anova)
    ss_total = sum((dom_data["z"] - grand_mean) ** 2)
    eta_sq = ss_between / ss_total if ss_total > 0 else 0

    tukey = pairwise_tukeyhsd(dom_data["z"], dom_data["cluster"])

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

    st.text("Tukey HSD post-hoc (cluster pairwise comparisons):")
    st.text(str(tukey))

    if mlm is not None:
        with st.expander("Mixed linear model summary (z ~ age_band + position, player random intercept)"):
            st.dataframe(mlm_summary)

    quad_coeffs = np.polyfit(dom_data["age"], dom_data["z"], deg=2)
    qc, qb, qa = quad_coeffs
    quad_peak_age = -qb / (2 * qc) if qc != 0 else None
    quad_poly = np.poly1d(quad_coeffs)
    quad_age_range = np.linspace(dom_data["age"].min(), dom_data["age"].max(), 200)
    quad_curve = quad_poly(quad_age_range)

    method_b_results[domain_name]["quadratic_peak_age"] = (
        float(quad_peak_age) if quad_peak_age is not None else None
    )

    fig_b = go.Figure()
    for c in cluster_stats.index:
        cluster_pts = dom_data[dom_data["cluster"] == c]
        fig_b.add_trace(go.Scatter(
            x=cluster_pts["age"], y=cluster_pts["z"],
            mode="markers", marker=dict(size=5, opacity=0.35),
            name=f"Cluster {c} (mean age {cluster_stats.loc[c, 'mean_age']:.1f})",
        ))
        fig_b.add_vline(
            x=cluster_stats.loc[c, "mean_age"], line_dash="dot",
            line_color="gray", opacity=0.5,
        )

    fig_b.add_trace(go.Scatter(
        x=quad_age_range, y=quad_curve, mode="lines",
        line=dict(color="deepskyblue", width=3), name="Quadratic fit",
    ))

    player_pts = dom_data[dom_data["player_id"] == player_id]
    if not player_pts.empty:
        fig_b.add_trace(go.Scatter(
            x=player_pts["age"], y=player_pts["z"],
            mode="markers", marker=dict(size=12, color="gold", line=dict(width=1, color="black")),
            name=f"{player_name}'s sessions",
        ))

    fig_b.add_vline(
        x=peak_age_b, line_dash="dash", line_color="crimson",
        annotation_text=f"Cluster peak: {peak_age_b:.1f}y", annotation_position="top left",
    )
    if quad_peak_age is not None and dom_data["age"].min() <= quad_peak_age <= dom_data["age"].max():
        fig_b.add_vline(
            x=quad_peak_age, line_dash="dash", line_color="deepskyblue",
            annotation_text=f"Curve peak: {quad_peak_age:.1f}y", annotation_position="top right",
        )

    fig_b.update_layout(
        title=f"{domain_name} — age vs. z-score: clusters + quadratic fit (gold = {player_name})",
        xaxis_title="Age", yaxis_title=f"{domain_name} z-score (within position)",
    )
    st.plotly_chart(fig_b, use_container_width=True)

    st.caption(
        f"Two peak estimates: **cluster peak** (crimson, {peak_age_b:.1f}y) from "
        f"the paper-replicated k-means pipeline, and **curve peak** (blue, "
        f"{f'{quad_peak_age:.1f}y' if quad_peak_age is not None else '—'}) from a "
        f"quadratic regression fit to the same data. Close agreement is a good "
        f"sign the peak is real rather than a single-method artifact."
    )

    if player_pts.empty:
        st.caption(f"{player_name} has no Catapult sessions matched for this domain.")
    else:
        player_avg_age = player_pts["age"].mean()
        distance_from_peak = player_avg_age - peak_age_b
        st.caption(
            f"{player_name}'s average age across these sessions: {player_avg_age:.1f} "
            f"({'above' if distance_from_peak > 0 else 'below'} the {domain_name.lower()} "
            f"peak by {abs(distance_from_peak):.1f} years)."
        )

st.markdown("---")
st.header("Method A vs. Method B — Summary Comparison")

method_a_peak = verdict_record["test_2"]["estimated_peak_age"]
comparison_rows = [{
    "Method": "Method A (quadratic regression, our metric)",
    "Cluster Peak Age": None,
    "Quadratic Peak Age": method_a_peak,
}]
for domain, res in method_b_results.items():
    comparison_rows.append({
        "Method": f"Method B — {domain} (Branquinho et al. replication)",
        "Cluster Peak Age": res["peak_age"],
        "Quadratic Peak Age": res.get("quadratic_peak_age"),
    })
st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

st.caption(
    "If Method A and Method B's peak ages land close together, that's "
    "convergent evidence from two independent methods and data operationalizations. "
    "If they diverge, that's a legitimate discussion point."
)

verdict_record["method_b"] = {
    "citation": "Branquinho et al. (2025), J. Funct. Morphol. Kinesiol. 10(4):385",
    "domains": method_b_results,
    "last_computed": datetime.now(timezone.utc).isoformat(),
}
with open("verdict_h3.json", "w") as f:
    json.dump(verdict_record, f, indent=2)