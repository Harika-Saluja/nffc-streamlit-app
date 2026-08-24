import streamlit as st
import duckdb
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
import statsmodels.formula.api as smf
import json
from datetime import datetime, timezone

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Workload & Injury Risk", layout="wide")
st.title("WORKLOAD & INJURY RISK")

# -------------------------------
# Shared term definitions (reused everywhere these appear)
# -------------------------------
LOAD_METRIC_DEFINITIONS = {
    "Sprint Load (sl_sum)": (
        "Inferred from Catapult naming conventions as a cumulative "
        "sprint-distance/intensity figure per session (`sl_sum`) — not "
        "yet confirmed against official documentation."
    ),
    "Acceleration Load (a_sum)": (
        "Inferred as a cumulative high-intensity acceleration figure "
        "per session (`a_sum`) — not yet confirmed against official "
        "documentation."
    ),
    "Player Load (pl_sum)": (
        "Inferred as a cumulative player-load figure per session, "
        "summed from GPS/accelerometer data (`pl_sum`) — not yet "
        "confirmed against official documentation."
    ),
    "Max Heart Rate (hr_max)": (
        "The player's maximum recorded heart rate for that session "
        "(`hr_max`) — not yet confirmed against official documentation."
    ),
}
LOAD_METRIC_HELP = "\n\n".join(f"**{k}** — {v}" for k, v in LOAD_METRIC_DEFINITIONS.items())

RAW_COL_DEFINITIONS = {
    "sl_sum": LOAD_METRIC_DEFINITIONS["Sprint Load (sl_sum)"],
    "a_sum": LOAD_METRIC_DEFINITIONS["Acceleration Load (a_sum)"],
    "pl_sum": LOAD_METRIC_DEFINITIONS["Player Load (pl_sum)"],
    "hr_max": LOAD_METRIC_DEFINITIONS["Max Heart Rate (hr_max)"],
}


# -------------------------------
# Load data
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups   AS SELECT * FROM read_parquet('lineups.parquet');
    CREATE TABLE injuries  AS SELECT * FROM read_parquet('injuries.parquet');
    CREATE TABLE catapult  AS SELECT * FROM read_parquet('catapult.parquet');
    CREATE TABLE crosswalk AS SELECT * FROM read_parquet('identity_crosswalk.parquet');
""")

# -------------------------------
# Sidebar – full player roster, with a three-state status dot:
# 🟢 no training-load data at all (many players won't have any)
# 🟡 has training-load data, no recorded injury
# 🔴 has training-load data AND a recorded injury
# -------------------------------
st.sidebar.title("Player Selector")

all_players = con.execute("""
    SELECT DISTINCT player_id, player_name FROM lineups ORDER BY player_name
""").df()

if all_players.empty:
    st.error("No players found in lineups.parquet.")
    st.stop()

catapult_players = con.execute("""
    SELECT DISTINCT x.statsbomb_player_id AS player_id
    FROM catapult c JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id IS NOT NULL
""").df()["player_id"]

injury_players = con.execute("""
    SELECT DISTINCT statsbomb_id AS player_id FROM injuries WHERE statsbomb_id IS NOT NULL
""").df()["player_id"]

all_players["has_catapult"] = all_players["player_id"].isin(catapult_players)
all_players["has_injury"] = all_players["player_id"].isin(injury_players)


def status_dot(row) -> str:
    if not row["has_catapult"]:
        return "🟢"
    return "🔴" if row["has_injury"] else "🟡"


all_players["display_label"] = all_players["player_name"] + " " + all_players.apply(status_dot, axis=1)

selected_label = st.sidebar.selectbox("Select Player", all_players["display_label"])
st.sidebar.caption(
    "🟢 : no training-load data at all · 🟡 : has training-load data, "
    "no recorded injury · 🔴 : has training-load data and a recorded "
    "injury"
)

matched_player = all_players.loc[all_players["display_label"] == selected_label]
if matched_player.empty:
    st.error("Selected player not found.")
    st.stop()
player_id = int(matched_player["player_id"].iloc[0])
player_name = matched_player["player_name"].iloc[0]

st.markdown("---")
st.header(player_name)

# -------------------------------
# Pull this player's workload sessions and injury spells
# -------------------------------
load_df = con.execute(f"""
    SELECT c.date, c.hr_max, c.sl_sum, c.a_sum, c.pl_sum
    FROM catapult c
    JOIN crosswalk x ON c.athlete_id = x.athlete_id
    WHERE x.statsbomb_player_id = {player_id}
    ORDER BY c.date
""").df()

injury_df = con.execute(f"""
    SELECT reason, "from" AS injury_start, until AS injury_end,
           days_missed, games_missed
    FROM injuries
    WHERE statsbomb_id = {player_id}
    ORDER BY "from"
""").df()

metric_map = {
    "Sprint Load (sl_sum)": "sl_sum",
    "Acceleration Load (a_sum)": "a_sum",
    "Player Load (pl_sum)": "pl_sum",
    "Max Heart Rate (hr_max)": "hr_max",
}

if load_df.empty:
    # NOTE: the pooled, population-level analysis further down doesn't
    # depend on this specific player having data — only these two
    # player-specific sections do. Skipping just these (instead of
    # st.stop()-ing the whole page) means the pooled Statistical
    # Analysis section, and its verdict_h2.json write, still run even
    # when the currently-selected player is a 🔴 (no matched data).
    st.info(
        f"No training-load (Catapult) data is available for "
        f"{player_name} at the moment — the player-specific charts "
        f"below are skipped for them, but the pooled analysis further "
        f"down doesn't depend on this player and still runs."
    )
else:
    load_df["date"] = pd.to_datetime(load_df["date"])
    if not injury_df.empty:
        injury_df["injury_start"] = pd.to_datetime(injury_df["injury_start"])
        injury_df["injury_end"] = pd.to_datetime(injury_df["injury_end"])

    # -------------------------------
    # Workload trend with injury periods shaded
    # -------------------------------
    st.subheader("Training Load Over Time")

    with st.expander("ℹ️ What does this chart show?"):
        st.markdown(LOAD_METRIC_HELP)
        st.markdown(
            "The line shows the selected load metric across all of this "
            "player's recorded training sessions. Shaded red regions mark "
            "periods when they were injured, based on recorded injury spells."
        )

    metric_choice = st.radio(
        "Load metric:", list(metric_map.keys()), horizontal=True, help=LOAD_METRIC_HELP,
    )
    col = metric_map[metric_choice]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=load_df["date"], y=load_df[col],
        mode="lines+markers", name=metric_choice,
    ))

    for _, row in injury_df.iterrows():
        fig.add_vrect(
            x0=row["injury_start"], x1=row["injury_end"],
            fillcolor="red", opacity=0.15, line_width=0,
            annotation_text=row["reason"] if pd.notna(row["reason"]) else "Injury",
            annotation_position="top left",
        )

    fig.update_layout(
        title=f"{player_name} — {metric_choice} (red = injury period)",
        xaxis_title="Date", yaxis_title=metric_choice,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"{player_name} has {len(injury_df)} recorded injury period(s) in "
        f"this window." if not injury_df.empty else
        f"{player_name} has no recorded injuries in this window."
    )

    # -------------------------------
    # Pre-injury load vs. season-average load (single player, illustrative)
    # -------------------------------
    st.markdown("---")
    st.subheader("Pre-Injury Load Check (This Player Only)")

    with st.expander("ℹ️ What does this table show?"):
        st.markdown(
            "For each of this player's recorded injuries, compares their "
            "average training load in the N days immediately before that "
            "injury to their overall average across all tracked sessions. "
            "This is illustrative for this one player only — not "
            "statistical evidence on its own. The pooled, population-level "
            "test is further below."
        )

    PLAYER_WINDOW_DAYS = st.slider("Look-back window before injury (days)", 3, 28, 14)

    if injury_df.empty:
        st.info(f"No injury records for {player_name} — nothing to compare.")
    else:
        season_avg = load_df[col].mean()
        rows = []
        for _, row in injury_df.iterrows():
            window_start = row["injury_start"] - pd.Timedelta(days=PLAYER_WINDOW_DAYS)
            pre_injury = load_df[
                (load_df["date"] >= window_start) & (load_df["date"] < row["injury_start"])
            ]
            rows.append({
                "Injury": row["reason"] if pd.notna(row["reason"]) else "Unspecified",
                "Date": row["injury_start"].date(),
                "Days Missed": row["days_missed"],
                f"Avg {metric_choice} ({PLAYER_WINDOW_DAYS}d before)": (
                    round(pre_injury[col].mean(), 2) if not pre_injury.empty else None
                ),
                "Overall Avg": round(season_avg, 2),
            })

        result_df = pd.DataFrame(rows)
        st.dataframe(result_df, use_container_width=True)
        st.caption(
            f"{player_name}'s pre-injury load compared to their overall "
            f"average, across {len(rows)} recorded injury period(s)."
        )

# ===========================================================
# STATISTICAL ANALYSIS — pooled across ALL players
# ===========================================================
st.markdown("---")
st.header("Statistical Analysis (All Players, Pooled)")

with st.expander("ℹ️ How are these player-windows built?"):
    st.markdown(
        "For every training session date a player has, we look back N "
        "days (chosen below) and sum/max their load over that span — "
        "an OVERLAPPING rolling window ending on each session date (not "
        "fixed blocks). Each window is labeled as preceding an injury "
        "if the player picks up an injury within a short follow-up "
        "period right after that window, otherwise not. Windows "
        "falling during an existing injury are excluded, since a "
        "player who's already out isn't generating a normal "
        "training-exposure window."
    )
    st.markdown(
        "**What the two sliders below actually do:** moving either one "
        "rebuilds every number and chart in this section from scratch, "
        "using a different window/follow-up definition — this is a way "
        "to check whether a finding holds up under different reasonable "
        "choices, rather than being an artifact of one specific choice. "
        "A wider window considers more training history before each "
        "injury; a shorter follow-up requires the injury to happen "
        "almost immediately after the window ends. If the verdict below "
        "stays roughly the same across different settings, that's a "
        "sign of a more robust finding — if it flips around a lot, "
        "that's worth treating with extra caution."
    )

WINDOW_DAYS = st.slider(
    "Sliding window size — how many days of training load to look back over (days)",
    3, 60, 14, key="pop_window_days",
)
FOLLOW_DAYS = st.slider(
    "Follow-up period — how soon after the window counts as 'led to injury' (days)",
    1, 14, 3, key="pop_follow_days",
)


@st.cache_data
def build_all_windows(window_days: int, follow_days: int) -> pd.DataFrame:
    all_load = con.execute("""
        SELECT x.statsbomb_player_id AS player_id, c.date,
               c.hr_max, c.sl_sum, c.a_sum, c.pl_sum
        FROM catapult c
        JOIN crosswalk x ON c.athlete_id = x.athlete_id
        WHERE x.statsbomb_player_id IS NOT NULL
        ORDER BY x.statsbomb_player_id, c.date
    """).df()
    all_load["date"] = pd.to_datetime(all_load["date"])

    all_inj = con.execute("""
        SELECT statsbomb_id AS player_id, "from" AS injury_start, until AS injury_end
        FROM injuries
        WHERE statsbomb_id IS NOT NULL
    """).df()
    all_inj["injury_start"] = pd.to_datetime(all_inj["injury_start"])
    all_inj["injury_end"] = pd.to_datetime(all_inj["injury_end"])

    window_rows = []
    for pid, sessions in all_load.groupby("player_id"):
        sessions = sessions.sort_values("date").set_index("date")
        player_inj = all_inj[all_inj["player_id"] == pid]

        rolled_sum = sessions[["sl_sum", "a_sum", "pl_sum"]].rolling(f"{window_days}D").sum()
        rolled_max = sessions[["hr_max"]].rolling(f"{window_days}D").max()
        windows = pd.concat([rolled_sum, rolled_max], axis=1).reset_index()
        windows["player_id"] = pid

        for _, inj in player_inj.iterrows():
            active = (windows["date"] >= inj["injury_start"]) & (windows["date"] <= inj["injury_end"])
            windows = windows[~active]

        windows["injury_occurred"] = 0
        for _, inj in player_inj.iterrows():
            lead_up = (
                (windows["date"] < inj["injury_start"])
                & (windows["date"] >= inj["injury_start"] - pd.Timedelta(days=follow_days))
            )
            windows.loc[lead_up, "injury_occurred"] = 1

        window_rows.append(windows)

    return pd.concat(window_rows, ignore_index=True) if window_rows else pd.DataFrame()


all_windows = build_all_windows(WINDOW_DAYS, FOLLOW_DAYS)
all_windows = all_windows.dropna(subset=["sl_sum", "a_sum", "pl_sum", "hr_max"])

n_injury_windows = int(all_windows["injury_occurred"].sum())
n_total_windows = len(all_windows)
st.caption(
    f"Built {n_total_windows} player-windows across "
    f"{all_windows['player_id'].nunique() if not all_windows.empty else 0} players "
    f"({n_injury_windows} labeled as preceding an injury)."
)

if n_injury_windows < 10 or n_total_windows - n_injury_windows < 10:
    st.warning(
        "Not enough windows in one or both groups to run the tests reliably "
        "at this window size — try a different window/follow-up length."
    )
    st.stop()

# -----------------------------------------------------------
# Load Before Injury vs. Normal Windows (Mann-Whitney U)
# -----------------------------------------------------------
st.subheader("Load Before Injury vs. Normal Windows")

with st.expander("ℹ️ What does this test check?"):
    st.markdown(
        "Compares the distribution of load values in windows that "
        "precede an injury against windows that don't, using the "
        "Mann-Whitney U test — a rank-based test that doesn't assume "
        "the data is normally distributed. p < 0.05 together with a "
        "positive effect size means load is significantly higher in "
        "windows that precede an injury."
    )

test_metric_choice = st.radio(
    "Metric to test:", list(metric_map.keys()), horizontal=True, key="test_metric",
    help=LOAD_METRIC_HELP,
)
test_col = metric_map[test_metric_choice]

injury_windows = all_windows[all_windows["injury_occurred"] == 1][test_col]
normal_windows = all_windows[all_windows["injury_occurred"] == 0][test_col]

u_stat, u_pval = stats.mannwhitneyu(injury_windows, normal_windows, alternative="two-sided")
n1, n2 = len(injury_windows), len(normal_windows)
rank_biserial = 1 - (2 * u_stat) / (n1 * n2)

box_fig = go.Figure()
box_fig.add_trace(go.Box(y=injury_windows, name=f"Pre-injury windows (n={n1})", marker_color="crimson"))
box_fig.add_trace(go.Box(y=normal_windows, name=f"Normal windows (n={n2})", marker_color="steelblue"))
box_fig.update_layout(
    title=f"{test_metric_choice} — windows preceding an injury vs. normal windows",
    yaxis_title=test_metric_choice,
)
st.plotly_chart(box_fig, use_container_width=True)
st.caption(
    "Each box shows the spread of load values in that group; if the "
    "two boxes barely overlap, load tends to be genuinely different "
    "before an injury — the metrics below give the formal test of that."
)

verdict1 = "SUPPORTED" if u_pval < 0.05 and rank_biserial > 0 else (
    "NOT SUPPORTED" if u_pval < 0.05 else "INCONCLUSIVE")
badge1 = {"SUPPORTED": "🔴", "NOT SUPPORTED": "🟢", "INCONCLUSIVE": "🟡"}[verdict1]

c1, c2, c3 = st.columns(3)
c1.metric("p-value", f"{u_pval:.4f}",
          help="Probability of seeing a difference this large by chance if there were truly no difference between the two groups. Below 0.05 is conventionally 'significant'.")
c2.metric("Effect size (rank-biserial)", f"{rank_biserial:+.3f}",
          help="Standardized measure of how much higher/lower pre-injury load ranks are compared to normal windows. Ranges -1 to +1; further from 0 means a bigger difference.")
c3.metric("Verdict", f"{badge1} {verdict1}",
          help="🔴 = load is significantly higher before injuries. 🟢 = no such pattern, or the opposite. 🟡 = inconclusive.")

# -----------------------------------------------------------
# Odds of Injury by Load (Logistic Regression)
# -----------------------------------------------------------
st.markdown("---")
st.subheader("Odds of Injury by Load")

with st.expander("ℹ️ What does this test check?"):
    st.markdown(
        "Fits a logistic regression predicting whether a window "
        "precedes an injury, using all four load metrics at once, each "
        "holding the others constant. An odds ratio above 1 means "
        "higher values of that metric are associated with higher odds "
        "of an injury following soon after; below 1 means the opposite."
    )

logit_model = smf.logit(
    "injury_occurred ~ sl_sum + a_sum + pl_sum + hr_max",
    data=all_windows,
).fit(disp=0)

summary_df = pd.DataFrame({
    "coef": logit_model.params,
    "pval": logit_model.pvalues,
    "ci_low": logit_model.conf_int()[0],
    "ci_high": logit_model.conf_int()[1],
}).drop("Intercept")

summary_df["odds_ratio"] = np.exp(summary_df["coef"])
summary_df["or_ci_low"] = np.exp(summary_df["ci_low"])
summary_df["or_ci_high"] = np.exp(summary_df["ci_high"])

forest_fig = go.Figure()
forest_fig.add_trace(go.Scatter(
    x=summary_df["odds_ratio"], y=summary_df.index,
    error_x=dict(
        type="data", symmetric=False,
        array=summary_df["or_ci_high"] - summary_df["odds_ratio"],
        arrayminus=summary_df["odds_ratio"] - summary_df["or_ci_low"],
    ),
    mode="markers", marker=dict(size=14, color="crimson"),
))
forest_fig.add_vline(x=1, line_dash="dash", line_color="gray")
forest_fig.update_layout(
    title="Odds ratio per load metric (95% CI) — dashed line = no effect",
    xaxis_title="Odds ratio",
)
st.plotly_chart(forest_fig, use_container_width=True)
st.caption(
    "Each dot is one metric's odds ratio with its 95% confidence "
    "interval. If the interval crosses the dashed line at 1, that "
    "metric's effect isn't statistically distinguishable from 'no "
    "effect' in this data."
)

# Term glossary using st.metric's tap-friendly help popover — the
# earlier HTML `title`-attribute approach only shows on mouse HOVER,
# which doesn't exist on touch devices, so the "?" marks were visible
# but did nothing when tapped. st.metric's help works on tap too.
glossary_row1 = st.columns(4)
glossary_row1[0].metric("sl_sum", "—", help=RAW_COL_DEFINITIONS["sl_sum"])
glossary_row1[1].metric("a_sum", "—", help=RAW_COL_DEFINITIONS["a_sum"])
glossary_row1[2].metric("pl_sum", "—", help=RAW_COL_DEFINITIONS["pl_sum"])
glossary_row1[3].metric("hr_max", "—", help=RAW_COL_DEFINITIONS["hr_max"])

glossary_row2 = st.columns(4)
glossary_row2[0].metric(
    "odds_ratio", "—",
    help="Multiplicative change in the odds of injury per one raw unit increase in that metric. 1 = no effect.",
)
glossary_row2[1].metric(
    "pval", "—",
    help="Probability of this odds ratio arising by chance if the true effect were zero. Below 0.05 is conventionally significant.",
)
glossary_row2[2].metric(
    "or_ci_low", "—",
    help="Lower bound of the 95% confidence interval for the odds ratio.",
)
glossary_row2[3].metric(
    "or_ci_high", "—",
    help="Upper bound of the 95% confidence interval for the odds ratio.",
)

st.dataframe(
    summary_df[["odds_ratio", "pval", "or_ci_low", "or_ci_high"]].round(4),
    use_container_width=True,
)

any_significant = (summary_df["pval"] < 0.05).any()
verdict2 = "SUPPORTED" if any_significant and (summary_df.loc[summary_df["pval"] < 0.05, "odds_ratio"] > 1).any() else (
    "NOT SUPPORTED" if any_significant else "INCONCLUSIVE")
badge2 = {"SUPPORTED": "🔴", "NOT SUPPORTED": "🟢", "INCONCLUSIVE": "🟡"}[verdict2]

st.metric("Overall Verdict", f"{badge2} {verdict2}",
          help="🔴 = at least one load metric shows significantly higher odds of injury. 🟢 = none do. 🟡 = mixed/unclear.")

st.caption(
    "NOTE: raw variables have very different scales (pl_sum in the "
    "millions, a_sum in the tens), so odds ratios here are per-raw-unit "
    "and not directly comparable across metrics — standardizing "
    "(z-score) each predictor first would give a fairer comparison of "
    "relative importance across metrics; not yet done here."
)

# ===========================================================
# SAVE VERDICT
# ===========================================================
verdict_record = {
    "hypothesis": "H2 — Workload & Injury Risk",
    "metric": test_metric_choice,
    "window_days": WINDOW_DAYS,
    "follow_days": FOLLOW_DAYS,
    "test_1": {
        "name": "Mann-Whitney U (Pre-Injury vs. Normal Windows)",
        "p_value": float(u_pval),
        "effect_size": float(rank_biserial),
        "verdict": verdict1,
    },
    "test_2": {
        "name": "Logistic Regression (Odds of Injury by Load)",
        "significant_predictors": summary_df[summary_df["pval"] < 0.05].index.tolist(),
        "odds_ratios": summary_df["odds_ratio"].round(4).to_dict(),
        "verdict": verdict2,
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h2.json", "w") as f:
    json.dump(verdict_record, f, indent=2)

# ===========================================================
# U-SHAPED INJURY RISK BY ACWR
# ===========================================================
st.markdown("---")
st.header("U-Shaped Injury Risk by Training Load Ratio (ACWR)")

with st.expander("ℹ️ What is ACWR, and what does 'U-shaped' mean here?"):
    st.markdown(
        "**ACWR (Acute:Chronic Workload Ratio)** compares a player's "
        "recent training load (the last 7 days — 'acute') to their "
        "longer-term baseline (the 21 days before that — 'chronic'): "
        "acute ÷ chronic. Around 1.0 means recent load matches their "
        "usual baseline; well below 1 suggests undertraining; well "
        "above 1 suggests a load spike."
    )
    st.markdown(
        "**Uncoupled:** the chronic window is shifted to end 7 days "
        "before the acute week starts, so the two windows never share "
        "the same days — avoiding an artificial correlation that a "
        "simple overlapping window would create."
    )
    st.markdown(
        "**U-shaped hypothesis:** the two tests above assume a roughly "
        "linear relationship — more load, more risk. This section "
        "checks a different idea instead: that injury risk could be "
        "elevated at BOTH extremes (undertraining AND large spikes), "
        "with a safer zone in between — rather than rising in a "
        "straight line. It does this by binning ACWR values and "
        "looking at the actual injury rate in each bin."
    )

acwr_metric_choice = st.radio(
    "Metric for ACWR:", list(metric_map.keys()), horizontal=True, key="acwr_metric",
    help=LOAD_METRIC_HELP,
)
acwr_col = metric_map[acwr_metric_choice]


@st.cache_data
def build_acwr_dataset(metric_col: str, follow_days: int) -> pd.DataFrame:
    all_load = con.execute("""
        SELECT x.statsbomb_player_id AS player_id, c.date,
               c.hr_max, c.sl_sum, c.a_sum, c.pl_sum
        FROM catapult c
        JOIN crosswalk x ON c.athlete_id = x.athlete_id
        WHERE x.statsbomb_player_id IS NOT NULL
        ORDER BY x.statsbomb_player_id, c.date
    """).df()
    all_load["date"] = pd.to_datetime(all_load["date"])

    all_inj = con.execute("""
        SELECT statsbomb_id AS player_id, "from" AS injury_start, until AS injury_end
        FROM injuries WHERE statsbomb_id IS NOT NULL
    """).df()
    all_inj["injury_start"] = pd.to_datetime(all_inj["injury_start"])
    all_inj["injury_end"] = pd.to_datetime(all_inj["injury_end"])

    rows = []
    for pid, sessions in all_load.groupby("player_id"):
        sessions = sessions.sort_values("date").set_index("date")
        player_inj = all_inj[all_inj["player_id"] == pid]

        acute = sessions[[metric_col]].rolling("7D").sum() / 7
        shifted = sessions[[metric_col]].shift(freq="7D")
        chronic = shifted.rolling("21D").sum() / 21

        acwr_df = acute.join(chronic, lsuffix="_acute", rsuffix="_chronic").reset_index()
        acwr_df.columns = ["date", "acute", "chronic"]
        acwr_df["acwr"] = acwr_df["acute"] / acwr_df["chronic"]
        acwr_df["player_id"] = pid
        acwr_df = acwr_df.replace([np.inf, -np.inf], np.nan).dropna(subset=["acwr"])

        for _, inj in player_inj.iterrows():
            active = (acwr_df["date"] >= inj["injury_start"]) & (acwr_df["date"] <= inj["injury_end"])
            acwr_df = acwr_df[~active]

        acwr_df["injury_occurred"] = 0
        for _, inj in player_inj.iterrows():
            lead_up = (
                (acwr_df["date"] < inj["injury_start"])
                & (acwr_df["date"] >= inj["injury_start"] - pd.Timedelta(days=follow_days))
            )
            acwr_df.loc[lead_up, "injury_occurred"] = 1

        rows.append(acwr_df)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


acwr_data = build_acwr_dataset(acwr_col, FOLLOW_DAYS)

if acwr_data.empty or len(acwr_data) < 50:
    st.warning("Not enough data to build the ACWR risk curve reliably.")
else:
    ACWR_BINS = [0, 0.8, 1.0, 1.3, 1.5, 2.0, 10]
    ACWR_BIN_LABELS = ["<0.8\n(undertrained)", "0.8-1.0", "1.0-1.3\n(safe)",
                        "1.3-1.5\n(caution)", "1.5-2.0\n(spike)", ">2.0\n(high spike)"]
    acwr_data["acwr_bin"] = pd.cut(acwr_data["acwr"], bins=ACWR_BINS, labels=ACWR_BIN_LABELS)

    bin_stats = acwr_data.groupby("acwr_bin", observed=True).agg(
        injury_rate=("injury_occurred", "mean"),
        n=("injury_occurred", "count"),
    ).reset_index()
    bin_stats["ci95"] = 1.96 * np.sqrt(
        bin_stats["injury_rate"] * (1 - bin_stats["injury_rate"]) / bin_stats["n"]
    )

    ushape_fig = go.Figure(go.Bar(
        x=bin_stats["acwr_bin"], y=bin_stats["injury_rate"],
        error_y=dict(type="data", array=bin_stats["ci95"]),
        marker_color="crimson",
        text=[f"n={n}" for n in bin_stats["n"]],
        textposition="outside",
    ))
    ushape_fig.update_layout(
        title=f"Injury rate by ACWR bin — {acwr_metric_choice}",
        xaxis_title="ACWR bin (uncoupled)", yaxis_title="Injury rate (proportion of windows)",
    )
    st.plotly_chart(ushape_fig, use_container_width=True)

    if len(bin_stats) >= 3:
        safe_idx = bin_stats[bin_stats["acwr_bin"].astype(str).str.contains("safe")].index
        if len(safe_idx) > 0:
            safe_rate = bin_stats.loc[safe_idx[0], "injury_rate"]
            is_lowest = safe_rate == bin_stats["injury_rate"].min()
            if is_lowest:
                st.success(
                    "✅ The 0.8-1.3 'safe' zone has the LOWEST injury rate "
                    "of all bins — consistent with a U-shaped relationship."
                )
            else:
                st.info(
                    "The 0.8-1.3 'safe' zone is NOT the lowest-risk bin in "
                    "this data — the U-shaped pattern isn't clearly "
                    "replicated here, worth noting as a genuine finding "
                    "rather than forcing the expected shape."
                )

    st.caption(
        f"Bars show the actual proportion of ACWR windows (per "
        f"player-date) that preceded an injury within {FOLLOW_DAYS} "
        f"days, by ACWR bin. Wide confidence intervals on sparse bins "
        f"(small n) should be read cautiously — this is exploratory, "
        f"not a formal statistical test."
    )