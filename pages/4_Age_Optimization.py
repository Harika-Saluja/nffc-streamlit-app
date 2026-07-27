import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
import scikit_posthocs as sp

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
    "in the bucket, so this tests performance by age only, not cost-"
    "adjusted value. **We are not assuming 24-27 is the peak** — every "
    "age bucket is compared against every other bucket, and the "
    "best-performing bucket is whichever one the data actually shows, "
    "not a bucket chosen in advance."
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

raw = raw.dropna(subset=["age_at_match"])
raw = raw[(raw["age_at_match"] >= 15) & (raw["age_at_match"] <= 45)]  # sanity bounds

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
# Every bucket compared against every other bucket — the best
# bucket is whichever the data shows, not assumed in advance.
# ===========================================================
st.markdown("---")
st.header("Test 1 — Age Bucket Comparison (Kruskal-Wallis + Dunn's Post-Hoc)")

bucket_groups = [data[data["age_bucket"] == b][col].dropna() for b in BUCKET_LABELS]
bucket_groups_valid = [(lbl, g) for lbl, g in zip(BUCKET_LABELS, bucket_groups) if len(g) >= 10]

if len(bucket_groups_valid) < 3:
    st.warning("Not enough data across enough buckets to run this test reliably.")
else:
    valid_labels = [lbl for lbl, _ in bucket_groups_valid]
    valid_groups = [g for _, g in bucket_groups_valid]

    h_stat, kw_pval = stats.kruskal(*valid_groups)

    # bucket means with 95% CI, best bucket highlighted (data-driven)
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
        "bucket — it doesn't say which. The full pairwise comparison below "
        "(Dunn's test) checks every bucket against every other bucket "
        "individually, with a Holm correction since running many pairwise "
        "tests inflates the false-positive rate if left uncorrected."
    )

    # ---- Full pairwise Dunn's test matrix ----
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
        title="Dunn's post-hoc p-values (Holm-corrected) — red/orange = significant difference (p<0.05)",
    )
    st.plotly_chart(heat_fig, use_container_width=True)

    # summarize which buckets the best bucket actually beats significantly
    if best_bucket in dunn_result.index:
        sig_vs_best = dunn_result.loc[best_bucket]
        beats = [b for b in valid_labels if b != best_bucket and sig_vs_best[b] < 0.05]
        not_sig = [b for b in valid_labels if b != best_bucket and sig_vs_best[b] >= 0.05]

        if beats:
            st.success(
                f"**{best_bucket}** significantly outperforms: {', '.join(beats)} "
                f"(p < 0.05 in each pairwise comparison)."
            )
        if not_sig:
            st.info(
                f"**{best_bucket}** is NOT significantly different from: "
                f"{', '.join(not_sig)} — the data can't confidently "
                f"distinguish these buckets from the best one."
            )

# ===========================================================
# TEST 2 — Quadratic regression on continuous age
# Finds the actual peak age from the data, not assumed.
# ===========================================================
st.markdown("---")
st.header("Test 2 — Peak Age (Quadratic Regression)")

reg_data = data.dropna(subset=["age_at_match", col])
X = reg_data["age_at_match"].values
y = reg_data[col].values

# fit y = a + b*age + c*age^2
coeffs = np.polyfit(X, y, deg=2)
c, b, a = coeffs  # numpy returns highest-degree first
poly = np.poly1d(coeffs)

peak_age = -b / (2 * c) if c != 0 else None
peak_value = poly(peak_age) if peak_age is not None else None

age_range = np.linspace(X.min(), X.max(), 200)
fitted_curve = poly(age_range)

scatter_fig = go.Figure()
scatter_fig.add_trace(go.Scatter(
    x=X, y=y, mode="markers", marker=dict(size=4, color="steelblue", opacity=0.2),
    name="Player-matches",
))
scatter_fig.add_trace(go.Scatter(
    x=age_range, y=fitted_curve, mode="lines",
    line=dict(color="crimson", width=3), name="Fitted quadratic curve",
))
if peak_age is not None and X.min() <= peak_age <= X.max():
    scatter_fig.add_vline(
        x=peak_age, line_dash="dash", line_color="gold",
        annotation_text=f"Model peak: age {peak_age:.1f}",
    )
scatter_fig.update_layout(
    title=f"{label} vs. age — fitted peak from the data",
    xaxis_title="Age at match", yaxis_title=label,
)
st.plotly_chart(scatter_fig, use_container_width=True)

is_downward_parabola = c < 0
in_2427_range = peak_age is not None and 24 <= peak_age <= 27

c1, c2, c3 = st.columns(3)
c1.metric("Estimated peak age", f"{peak_age:.1f}" if peak_age is not None else "—")
c2.metric("Shape", "Peaks then declines" if is_downward_parabola else "No clear peak (keeps rising/falling)")
c3.metric("Falls in 24-27 range?", "Yes" if in_2427_range else "No")

st.caption(
    "This model doesn't yet account for repeated observations from the "
    "same player (a prolific player contributes many rows across many "
    "ages) — a mixed-effects quadratic model "
    "(per90 ~ age + age² + (1|player_id)) would control for that and is "
    "a reasonable next step if this result needs to hold up to scrutiny. "
    "Treat this as a first-pass population estimate of the peak."
)