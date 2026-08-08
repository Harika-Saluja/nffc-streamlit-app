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
st.set_page_config(page_title="Squad Optimizer", layout="wide")
st.title("Squad Optimizer")
st.caption(
    "H4: Squads with more balanced composition — specifically cultural/"
    "national diversity — produce more consistent results. Combines a "
    "team-level analysis (Maderer, Holtbrügge & Schuster, 2014) with an "
    "individual-level analysis (Lago, Lago-Peñas & Lago-Peñas, 2023)."
)
st.warning(
    "**Scope notes:** (1) 'Nationality' here is StatsBomb's `country` field "
    "per player — a proxy for the cultural/ethnic background both papers "
    "actually use, not a verified ethnicity measure. (2) Neither paper's "
    "coach-experience factor can be replicated — no coach data exists "
    "anywhere in this project's sources. (3) Lago et al.'s original outcome "
    "is Transfermarkt market value change; here we substitute our own "
    "per-90 performance composite — a different outcome variable using "
    "their method, not a replication of their exact result."
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

has_country = "country" in con.execute("DESCRIBE lineups").df()["column_name"].values
if not has_country:
    st.error(
        "`lineups.parquet` has no `country` column — this page needs the "
        "rebuild step (see build_all_datasets_v2.py Section 2) run first. "
        "Nothing below will work until that's rebuilt."
    )
    st.stop()

# League -> home country, used to determine "native" vs "foreign" per player
LEAGUE_COUNTRY = {
    "Premier League": "England",
    "La Liga": "Spain",
    "Serie A": "Italy",
    "1. Bundesliga": "Germany",
    "Ligue 1": "France",
}

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

# -------------------------------
# Build base player-team-season table
# -------------------------------
raw = con.execute("""
    SELECT
        l.player_id, l.player_name, l.team_name, l.country, l.birth_date,
        l.minutes_played, l.match_id,
        m.season, m.competition, m.match_date,
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
raw["home_country"] = raw["competition"].map(LEAGUE_COUNTRY)
raw["is_foreign"] = raw["country"].notna() & (raw["country"] != raw["home_country"])

METRIC_MAP = {
    "xG per 90": "xg_90",
    "Pass Success %": "pass_success_mean",
}
metric_choice = st.radio("Performance metric:", list(METRIC_MAP.keys()), horizontal=True)
col = METRIC_MAP[metric_choice]

# -------------------------------
# Team-season aggregates: nationality diversity + points-per-game
# -------------------------------
team_season = raw.groupby(["team_name", "season", "competition"])["country"].apply(
    lambda s: 1 - sum((s.value_counts(normalize=True)) ** 2)  # Blau index
).reset_index(name="blau_diversity")

team_season_perf = raw.groupby(["team_name", "season"])[col].mean().reset_index()
team_season = team_season.merge(team_season_perf, on=["team_name", "season"])


def team_ppg(team, season):
    m = con.execute(f"""
        SELECT home_team, away_team, home_score, away_score
        FROM matches WHERE season = '{season}'
          AND (home_team = '{team}' OR away_team = '{team}')
    """).df()
    if m.empty:
        return None
    points = []
    for _, r in m.iterrows():
        if r["home_team"] == team:
            gf, ga = r["home_score"], r["away_score"]
        else:
            gf, ga = r["away_score"], r["home_score"]
        points.append(3 if gf > ga else (1 if gf == ga else 0))
    return np.mean(points)


team_season["ppg"] = team_season.apply(lambda r: team_ppg(r["team_name"], r["season"]), axis=1)
team_season = team_season.dropna(subset=["ppg", "blau_diversity"])

# ===========================================================
# TEAM-LEVEL ANALYSIS (Maderer, Holtbrügge & Schuster, 2014)
# ===========================================================
st.header("Team-Level: Cultural Diversity vs. Results (Maderer et al., 2014)")

st.caption(
    "Blau index of nationality diversity per squad-season "
    "(1 − Σpᵢ², where pᵢ is the proportion of players from country i) "
    "vs. points-per-game that season. Maderer et al. found a NEGATIVE "
    "relationship — worth checking whether this data shows the same."
)

if len(team_season) < 10:
    st.warning("Not enough team-seasons to run this analysis reliably.")
else:
    rho, spearman_p = stats.spearmanr(team_season["blau_diversity"], team_season["ppg"])

    scatter_fig = go.Figure(go.Scatter(
        x=team_season["blau_diversity"], y=team_season["ppg"],
        mode="markers", marker=dict(size=8, color="steelblue", opacity=0.6),
        text=team_season["team_name"] + " (" + team_season["season"] + ")",
        hoverinfo="text+x+y",
    ))
    z = np.polyfit(team_season["blau_diversity"], team_season["ppg"], 1)
    trend_x = np.linspace(team_season["blau_diversity"].min(), team_season["blau_diversity"].max(), 50)
    scatter_fig.add_trace(go.Scatter(
        x=trend_x, y=np.poly1d(z)(trend_x), mode="lines",
        line=dict(color="crimson", width=2), name="Trend",
    ))
    scatter_fig.update_layout(
        title="Squad nationality diversity vs. points-per-game",
        xaxis_title="Blau diversity index (0 = homogeneous, →1 = diverse)",
        yaxis_title="Points per game",
    )
    st.plotly_chart(scatter_fig, use_container_width=True)

    verdict_team = "SIGNIFICANT RELATIONSHIP" if spearman_p < 0.05 else "NO SIGNIFICANT RELATIONSHIP"
    badge_team = "🔴" if spearman_p < 0.05 else "🟢"
    c1, c2, c3 = st.columns(3)
    c1.metric("Spearman ρ", f"{rho:+.3f}")
    c2.metric("p-value", f"{spearman_p:.4f}")
    c3.metric("Verdict", f"{badge_team} {verdict_team}")

    direction_note = (
        "negative — consistent with Maderer et al.'s finding" if rho < 0
        else "positive — the OPPOSITE direction of Maderer et al.'s finding"
    )
    st.caption(f"Relationship direction: {direction_note}.")

# ===========================================================
# INDIVIDUAL-LEVEL ANALYSIS (Lago, Lago-Peñas & Lago-Peñas, 2023)
# ===========================================================
st.markdown("---")
st.header("Individual-Level: Newcomer Performance (Lago et al., 2023)")

st.caption(
    "For players new to a specific CLUB (not just new to the dataset), "
    "does being foreign (per StatsBomb's country field vs. the club's "
    "home country) predict performance — and does that effect depend on "
    "player age or on how many other new signings joined the same club "
    "that season (subgroup imbalance)? OLS with standard errors clustered "
    "by team, following Lago et al.'s Method section exactly."
)

# first season a player appears for EACH specific team (not just first
# season in the dataset overall — a player transferring between two
# tracked clubs should be flagged "new" again at the second club)
player_team_first_season = raw.groupby(["player_id", "team_name"])["season"].min().reset_index()
player_team_first_season = player_team_first_season.rename(columns={"season": "first_season_at_team"})

newcomers = raw.merge(player_team_first_season, on=["player_id", "team_name"])
newcomers = newcomers[newcomers["season"] == newcomers["first_season_at_team"]]

# subgroup imbalance proxy: number of OTHER new signings at the same
# club that season (Lago et al.'s "# of Transfers" — fewer new signings
# means the newcomer is more of an outlier against an established squad)
signings_per_team_season = newcomers.groupby(["team_name", "season"])["player_id"].nunique().reset_index(
    name="n_new_signings"
)
newcomers = newcomers.merge(signings_per_team_season, on=["team_name", "season"])

# collapse to one row per player-team-season (average across their
# matches that first season) for the regression
individual_data = newcomers.groupby(
    ["player_id", "player_name", "team_name", "season", "is_foreign", "n_new_signings"]
).agg(
    performance=(col, "mean"),
    age=("age_at_match", "mean"),
).reset_index().dropna(subset=["performance", "age"])

individual_data["is_foreign_int"] = individual_data["is_foreign"].astype(int)

if len(individual_data) < 30 or individual_data["team_name"].nunique() < 5:
    st.warning("Not enough newcomer data to run this regression reliably.")
else:
    try:
        model = smf.ols(
            "performance ~ is_foreign_int * age + is_foreign_int * n_new_signings",
            data=individual_data,
        ).fit(cov_type="cluster", cov_kwds={"groups": individual_data["team_name"]})

        summary_df = pd.DataFrame({
            "coef": model.params,
            "std_err": model.bse,
            "pval": model.pvalues,
        }).drop("Intercept")

        forest_fig = go.Figure()
        forest_fig.add_trace(go.Scatter(
            x=summary_df["coef"], y=summary_df.index,
            error_x=dict(type="data", array=1.96 * summary_df["std_err"]),
            mode="markers", marker=dict(size=12, color="crimson"),
        ))
        forest_fig.add_vline(x=0, line_dash="dash", line_color="gray")
        forest_fig.update_layout(
            title=f"OLS coefficients — {metric_choice} (clustered SE by team)",
            xaxis_title="Coefficient",
        )
        st.plotly_chart(forest_fig, use_container_width=True)

        st.dataframe(summary_df.round(4), use_container_width=True)

        foreign_age_p = model.pvalues.get("is_foreign_int:age")
        foreign_signings_p = model.pvalues.get("is_foreign_int:n_new_signings")

        verdict_ind = "INCONCLUSIVE"
        if foreign_age_p is not None and foreign_signings_p is not None:
            if foreign_age_p < 0.05 or foreign_signings_p < 0.05:
                verdict_ind = "SIGNIFICANT INTERACTION FOUND"
            else:
                verdict_ind = "NO SIGNIFICANT INTERACTION"
        badge_ind = "🔴" if verdict_ind == "SIGNIFICANT INTERACTION FOUND" else "🟢"

        c1, c2, c3 = st.columns(3)
        c1.metric("Foreign × Age p-value", f"{foreign_age_p:.4f}" if foreign_age_p is not None else "—")
        c2.metric("Foreign × New Signings p-value", f"{foreign_signings_p:.4f}" if foreign_signings_p is not None else "—")
        c3.metric("Verdict", f"{badge_ind} {verdict_ind}")

        st.caption(
            f"n={len(individual_data)} newcomer player-team-seasons across "
            f"{individual_data['team_name'].nunique()} teams. Lago et al. found "
            f"foreign newcomers perform BETTER when younger and when subgroup "
            f"imbalance is high (few other new signings) — check whether the "
            f"coefficient signs above match that pattern."
        )

        # highlight selected player if they appear in the newcomer set
        player_row = individual_data[individual_data["player_id"] == player_id]
        if not player_row.empty:
            st.markdown(f"**📍 {player_name} in this analysis:**")
            st.dataframe(player_row[["team_name", "season", "is_foreign", "age", "n_new_signings", "performance"]],
                         use_container_width=True, hide_index=True)
        else:
            st.caption(f"{player_name} is not a newcomer in this dataset's tracked window "
                       f"(no team-change detected), so they don't appear in this regression.")

    except Exception as e:
        st.error(f"Model could not be fit: {e}")
        model = None

# ===========================================================
# SAVE VERDICT
# ===========================================================
verdict_record = {
    "hypothesis": "H4 — Squad Balance",
    "metric": metric_choice,
    "team_level": {
        "name": "Blau Diversity Index vs. PPG (Maderer et al., 2014)",
        "spearman_rho": float(rho) if len(team_season) >= 10 else None,
        "p_value": float(spearman_p) if len(team_season) >= 10 else None,
        "verdict": verdict_team if len(team_season) >= 10 else "NOT COMPUTED",
    },
    "individual_level": {
        "name": "Newcomer Performance OLS (Lago et al., 2023)",
        "foreign_age_interaction_p": float(foreign_age_p) if 'foreign_age_p' in dir() and foreign_age_p is not None else None,
        "foreign_signings_interaction_p": float(foreign_signings_p) if 'foreign_signings_p' in dir() and foreign_signings_p is not None else None,
        "verdict": verdict_ind if 'verdict_ind' in dir() else "NOT COMPUTED",
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h4.json", "w") as f:
    json.dump(verdict_record, f, indent=2)