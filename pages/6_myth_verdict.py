import streamlit as st
import json
import os
from datetime import datetime

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Myth Verdict Dashboard", layout="wide")
st.title("Myth Verdict Dashboard")
st.caption(
    "Pulls the real, already-computed statistical results from each "
    "hypothesis's own page. If a hypothesis shows 'Not yet computed', "
    "visit that page first — visiting it runs the tests and saves the "
    "result here automatically."
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
    "Verdicts are pulled live from each hypothesis page's own saved "
    "results — refresh this page after revisiting H1/H2/H3 to see "
    "updated numbers if you've changed any sliders or settings there."
)