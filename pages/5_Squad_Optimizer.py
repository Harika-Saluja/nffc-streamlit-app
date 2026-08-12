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
st.title("SQUAD OPTIMIZER")

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
        "rebuild step run first. Nothing below will work until that's "
        "rebuilt."
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

METRIC_MAP = {"xG per 90": "xg_90", "Pass Success %": "pass_success_mean"}
METRIC_DEFINITIONS = {
    "xG per 90": (
        "**xG per 90** — Expected Goals per 90 minutes: shot quality "
        "summed across a player's matches that season, divided by "
        "minutes played, scaled to a 90-minute rate."
    ),
    "Pass Success %": (
        "**Pass Success %** — the average, across a player's matches, "
        "of each match's own mean pass-success probability — not "
        "weighted by how many passes were actually attempted."
    ),
}
METRIC_DEFINITIONS_HELP = "\n\n".join(METRIC_DEFINITIONS.values())


def detect_all_league_switches(player_rows: pd.DataFrame):
    """Every genuine league switch across a player's tracked seasons —
    a competition change between two consecutive seasons, with the team
    played for on each side of the switch. Returns a list (possibly
    empty, possibly more than one entry for multiple switches)."""
    seasons_sorted = sorted(player_rows["season"].dropna().unique())
    switches = []
    for i in range(1, len(seasons_sorted)):
        prev_rows = player_rows[player_rows["season"] == seasons_sorted[i - 1]]
        curr_rows = player_rows[player_rows["season"] == seasons_sorted[i]]
        prev_leagues = set(prev_rows["competition"].dropna())
        curr_leagues = set(curr_rows["competition"].dropna())
        if prev_leagues and curr_leagues and not (prev_leagues & curr_leagues):
            prev_team_mode = prev_rows["team_name"].mode()
            curr_team_mode = curr_rows["team_name"].mode()
            switches.append({
                "from_league": list(prev_leagues)[0],
                "to_league": list(curr_leagues)[0],
                "from_season": seasons_sorted[i - 1],
                "to_season": seasons_sorted[i],
                "from_team": prev_team_mode.iloc[0] if not prev_team_mode.empty else None,
                "to_team": curr_team_mode.iloc[0] if not curr_team_mode.empty else None,
            })
    return switches


# -------------------------------
# Sidebar – full player roster, with a league-change indicator per player
# -------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name FROM lineups ORDER BY player_name
""").df()
if players.empty:
    st.error("No players found in lineups.parquet.")
    st.stop()

lightweight_ps = con.execute("""
    SELECT DISTINCT l.player_id, l.team_name, m.season, m.competition
    FROM lineups l JOIN matches m ON l.match_id = m.match_id
""").df()

move_status = pd.Series(
    {pid: bool(detect_all_league_switches(g)) for pid, g in lightweight_ps.groupby("player_id")},
    name="has_moved",
)
move_status.index.name = "player_id"
players = players.merge(move_status, on="player_id", how="left")
players["has_moved"] = players["has_moved"].fillna(False)
players["display_label"] = players["player_name"] + players["has_moved"].map({True: " 🟢", False: " 🔴"})

selected_label = st.sidebar.selectbox("Select Player", players["display_label"])
st.sidebar.caption("🟢 : changed leagues within the tracked window · 🔴 : no detected league change")

matched = players.loc[players["display_label"] == selected_label]
if matched.empty:
    st.error("Selected player not found.")
    st.stop()
player_id = int(matched["player_id"].iloc[0])
player_name = matched["player_name"].iloc[0]

player_switches = detect_all_league_switches(lightweight_ps[lightweight_ps["player_id"] == player_id])
the_move = player_switches[-1] if player_switches else None  # most recent, if any

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


def team_ppg(team, season, _con):
    m = _con.execute(f"""
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


# ===========================================================
# TEAM-LEVEL ANALYSIS
# ===========================================================
st.header("Team-Level: Cultural Diversity vs. Results")

team_metric_choice = st.radio(
    "Performance metric:", list(METRIC_MAP.keys()), horizontal=True,
    key="team_metric", help=METRIC_DEFINITIONS_HELP,
)
team_col = METRIC_MAP[team_metric_choice]

with st.expander("ℹ️ What is the diversity index and what does this chart show?"):
    st.markdown(
        "**Diversity index (Blau index):** `1 − Σpᵢ²`, where pᵢ is the "
        "share of a squad's players from country i, based on each "
        "player's `country` field. 0 = every player is the same "
        "nationality; closer to 1 = many nationalities represented "
        "roughly evenly. This is a standard diversity formula, not "
        "something built specifically for football."
    )
    st.markdown(
        "**What the chart shows:** each dot is one team-season — its "
        "diversity index on the x-axis, points-per-game that season on "
        "the y-axis. The red line is a simple linear trend through all "
        "the dots."
    )
    st.markdown(
        f"**The highlighted diamond:** marks {player_name}'s own "
        f"team-season(s) among the population, so you can see where "
        f"their squad(s) sit on both diversity and results."
    )

team_season = raw.groupby(["team_name", "season", "competition"])["country"].apply(
    lambda s: 1 - sum((s.value_counts(normalize=True)) ** 2)
).reset_index(name="blau_diversity")

team_season_perf = raw.groupby(["team_name", "season"])[team_col].mean().reset_index()
team_season = team_season.merge(team_season_perf, on=["team_name", "season"])
team_season["ppg"] = team_season.apply(lambda r: team_ppg(r["team_name"], r["season"], con), axis=1)
team_season = team_season.dropna(subset=["ppg", "blau_diversity"])

if len(team_season) < 10:
    st.warning("Not enough team-seasons to run this analysis reliably.")
else:
    rho, spearman_p = stats.spearmanr(team_season["blau_diversity"], team_season["ppg"])

    def diversity_scatter(data: pd.DataFrame, title: str, highlight_team: str = None, highlight_season: str = None):
        fig = go.Figure(go.Scatter(
            x=data["blau_diversity"], y=data["ppg"],
            mode="markers", marker=dict(size=8, color="steelblue", opacity=0.6),
            text=data["team_name"] + " (" + data["season"] + ")",
            hoverinfo="text+x+y", name="Team-seasons",
        ))
        if len(data) >= 2:
            z = np.polyfit(data["blau_diversity"], data["ppg"], 1)
            trend_x = np.linspace(data["blau_diversity"].min(), data["blau_diversity"].max(), 50)
            fig.add_trace(go.Scatter(
                x=trend_x, y=np.poly1d(z)(trend_x), mode="lines",
                line=dict(color="crimson", width=2), name="Trend",
            ))
        if highlight_team is not None and highlight_season is not None:
            hl = data[(data["team_name"] == highlight_team) & (data["season"] == highlight_season)]
            if not hl.empty:
                fig.add_trace(go.Scatter(
                    x=hl["blau_diversity"], y=hl["ppg"],
                    mode="markers", marker=dict(size=16, color="gold", symbol="diamond", line=dict(width=1, color="black")),
                    name=f"{player_name} ({highlight_team})",
                ))
        fig.update_layout(
            title=title,
            xaxis_title="Diversity index (0 = homogeneous, →1 = diverse)",
            yaxis_title="Points per game",
        )
        return fig

    if the_move is not None:
        # Mover: two separate charts, each filtered to the player's own
        # league on that side of the move, so you can compare where
        # their old squad sat vs. their new squad among LEAGUE PEERS.
        st.caption(
            f"{player_name} changed leagues ({the_move['from_league']} → "
            f"{the_move['to_league']}) — shown as two separate charts "
            f"below, each scoped to that league's own team-seasons."
        )
        col_a, col_b = st.columns(2)
        with col_a:
            from_data = team_season[team_season["competition"] == the_move["from_league"]]
            st.plotly_chart(
                diversity_scatter(from_data, f"{the_move['from_league']} ({the_move['from_season']})",
                                   the_move["from_team"], the_move["from_season"]),
                use_container_width=True,
            )
        with col_b:
            to_data = team_season[team_season["competition"] == the_move["to_league"]]
            st.plotly_chart(
                diversity_scatter(to_data, f"{the_move['to_league']} ({the_move['to_season']})",
                                   the_move["to_team"], the_move["to_season"]),
                use_container_width=True,
            )
    else:
        own_team = raw.loc[raw["player_id"] == player_id, "team_name"]
        own_season = raw.loc[raw["player_id"] == player_id, "season"]
        highlight_team = own_team.mode().iloc[0] if not own_team.empty and not own_team.mode().empty else None
        highlight_season = own_season.mode().iloc[0] if not own_season.empty and not own_season.mode().empty else None
        st.plotly_chart(
            diversity_scatter(team_season, "Squad diversity vs. points-per-game (all tracked team-seasons)",
                               highlight_team, highlight_season),
            use_container_width=True,
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Diversity–results correlation (ρ)", f"{rho:+.3f}",
               help="Spearman rank correlation between squad diversity and points-per-game across all tracked team-seasons. Ranges -1 to +1.")
    c2.metric("p-value", f"{spearman_p:.4f}",
               help="Probability of seeing a correlation this strong by chance alone if there were truly no relationship. Below 0.05 is conventionally 'statistically significant'.")
    verdict_team = "SIGNIFICANT RELATIONSHIP" if spearman_p < 0.05 else "NO SIGNIFICANT RELATIONSHIP"
    badge_team = "🔴" if spearman_p < 0.05 else "🟢"
    c3.metric("Verdict", f"{badge_team} {verdict_team}",
               help="🔴 = a statistically significant relationship was found (direction noted below). 🟢 = no significant relationship detected in this data.")

    direction_note = (
        "negative — more diverse squads tend to have a lower points-per-game in this data"
        if rho < 0 else
        "positive — more diverse squads tend to have a higher points-per-game in this data"
    )
    st.caption(
        f"Relationship direction: {direction_note}. This is a "
        f"correlation across all tracked team-seasons, not proof of "
        f"cause and effect in either direction."
    )

# ===========================================================
# INDIVIDUAL-LEVEL ANALYSIS
# ===========================================================
st.markdown("---")
st.header("Individual-Level: Newcomer Performance")

ind_metric_choice = st.radio(
    "Performance metric:", list(METRIC_MAP.keys()), horizontal=True,
    key="ind_metric", help=METRIC_DEFINITIONS_HELP,
)
ind_col = METRIC_MAP[ind_metric_choice]

with st.expander("ℹ️ What does 'newcomer' mean here and how is this calculated?"):
    st.markdown(
        "**Newcomer:** a player's FIRST tracked season at a SPECIFIC "
        "club — not just their first season in the dataset overall. A "
        "player transferring between two tracked clubs is flagged as a "
        "newcomer again at the second club."
    )
    st.markdown(
        "**Foreign:** the player's `country` field differs from the "
        "club's home-league country (e.g. a non-English player at a "
        "Premier League club) — a proxy for cultural background, not a "
        "verified ethnicity or cultural-background measure."
    )
    st.markdown(
        "**Subgroup imbalance (`n_new_signings`):** how many OTHER "
        "newcomers joined the same club that same season. Fewer other "
        "new signings means this player stands out more against an "
        "otherwise settled squad."
    )
    st.markdown(
        "**The regression:** tests whether being foreign predicts "
        "performance, and whether that effect depends on age or on "
        "subgroup imbalance — with standard errors clustered by team, "
        "so players from the same club aren't treated as fully "
        "independent observations."
    )
    st.markdown(
        "**Prerequisite:** this only says something meaningful about a "
        "SPECIFIC player if they actually changed clubs (or league) "
        "within the tracked window — a player who never moved doesn't "
        "appear as a newcomer anywhere in this regression."
    )

player_team_first_season = raw.groupby(["player_id", "team_name"])["season"].min().reset_index()
player_team_first_season = player_team_first_season.rename(columns={"season": "first_season_at_team"})

newcomers = raw.merge(player_team_first_season, on=["player_id", "team_name"])
newcomers = newcomers[newcomers["season"] == newcomers["first_season_at_team"]]

signings_per_team_season = newcomers.groupby(["team_name", "season"])["player_id"].nunique().reset_index(
    name="n_new_signings"
)
newcomers = newcomers.merge(signings_per_team_season, on=["team_name", "season"])

individual_data = newcomers.groupby(
    ["player_id", "player_name", "team_name", "season", "is_foreign", "n_new_signings"]
).agg(
    performance=(ind_col, "mean"),
    age=("age_at_match", "mean"),
).reset_index().dropna(subset=["performance", "age"])

individual_data["is_foreign_int"] = individual_data["is_foreign"].astype(int)

foreign_age_p = foreign_signings_p = None
verdict_ind = "NOT COMPUTED"

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
            title=f"OLS coefficients — {ind_metric_choice} (clustered standard errors by team)",
            xaxis_title="Coefficient",
        )
        st.plotly_chart(forest_fig, use_container_width=True)
        st.caption(
            "Each dot is one coefficient's estimate, with its 95% "
            "confidence interval. If a coefficient's interval crosses "
            "the dashed zero line, that effect isn't statistically "
            "distinguishable from zero in this data."
        )

        with st.expander("ℹ️ What do these terms mean?"):
            st.markdown("**is_foreign_int** — 1 if the player is foreign (see definition above), 0 if domestic. The effect of simply being foreign, on its own.")
            st.markdown("**age** — the newcomer's age. The effect of age, for domestic players specifically.")
            st.markdown("**is_foreign_int:age** — whether the effect of age differs for foreign vs. domestic newcomers (the interaction term).")
            st.markdown("**n_new_signings** — the effect of subgroup imbalance, for domestic players specifically.")
            st.markdown("**is_foreign_int:n_new_signings** — whether the effect of subgroup imbalance differs for foreign vs. domestic newcomers.")

        st.dataframe(summary_df.round(4), use_container_width=True)
        st.caption(
            "coef = estimated effect on the chosen performance metric. "
            "std_err = uncertainty around that estimate. pval = "
            "probability of an effect this large by chance if the true "
            "effect were zero (below 0.05 is conventionally "
            "'significant')."
        )

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
        c1.metric("Foreign × Age p-value", f"{foreign_age_p:.4f}" if foreign_age_p is not None else "—",
                   help="Tests whether age affects foreign newcomers' performance differently than domestic newcomers' performance.")
        c2.metric("Foreign × New Signings p-value", f"{foreign_signings_p:.4f}" if foreign_signings_p is not None else "—",
                   help="Tests whether subgroup imbalance (how many other newcomers arrived) affects foreign newcomers differently than domestic newcomers.")
        c3.metric("Verdict", f"{badge_ind} {verdict_ind}",
                   help="🔴 = at least one interaction is statistically significant. 🟢 = neither interaction is significant in this data.")

        st.caption(
            f"n={len(individual_data)} newcomer player-team-seasons "
            f"across {individual_data['team_name'].nunique()} teams."
        )

        if the_move is None:
            st.info(
                f"{player_name} hasn't changed leagues or clubs in this "
                f"dataset's tracked window, so they aren't part of this "
                f"newcomer regression specifically — the result above "
                f"still reflects the full population, just without a "
                f"player-specific highlight."
            )
        else:
            player_row = individual_data[individual_data["player_id"] == player_id]
            if not player_row.empty:
                st.markdown(f"**📍 {player_name} in this analysis (as a newcomer at {the_move['to_team']}):**")
                st.dataframe(
                    player_row[["team_name", "season", "is_foreign", "age", "n_new_signings", "performance"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption(
                    f"{player_name} changed leagues, but doesn't currently "
                    f"meet this regression's data requirements (e.g. missing "
                    f"age or performance data for that season) — so they "
                    f"don't appear in the table above."
                )

    except Exception as e:
        st.error(f"Model could not be fit: {e}")

# ===========================================================
# OVERALL RESULT
# ===========================================================
st.markdown("---")
st.header("Overall Result")

result_lines = []

if len(team_season) >= 10:
    team_dot = "🔴" if spearman_p < 0.05 else "🟢"
    result_lines.append(
        f"{team_dot} **Team-level:** squad diversity and points-per-game "
        f"show a {direction_note.split(' — ')[0]} relationship "
        f"(ρ={rho:+.3f}, p={spearman_p:.4f})."
    )
else:
    result_lines.append("🟡 **Team-level:** not enough team-seasons to compute a reliable result.")

if verdict_ind == "NOT COMPUTED":
    result_lines.append("🟡 **Individual-level:** not enough newcomer data to compute a reliable result.")
else:
    ind_dot = "🔴" if verdict_ind == "SIGNIFICANT INTERACTION FOUND" else "🟢"
    result_lines.append(f"{ind_dot} **Individual-level:** {verdict_ind.replace('_', ' ').title()}.")

if the_move is None:
    result_lines.append(
        f"⚪ {player_name} hasn't changed leagues in this dataset's "
        f"tracked window, so the individual-level (newcomer) result "
        f"above doesn't apply to them personally — only the team-level "
        f"result and chart do."
    )
else:
    result_lines.append(
        f"⚪ {player_name} moved from **{the_move['from_team']}** "
        f"({the_move['from_league']}, {the_move['from_season']}) to "
        f"**{the_move['to_team']}** ({the_move['to_league']}, "
        f"{the_move['to_season']}) — both the team-level charts and "
        f"the individual-level newcomer result above reflect this move."
    )

for line in result_lines:
    st.markdown(f"- {line}")

# ===========================================================
# SAVE VERDICT
# ===========================================================
verdict_record = {
    "hypothesis": "H4 — Squad Balance",
    "team_metric": team_metric_choice,
    "individual_metric": ind_metric_choice,
    "team_level": {
        "name": "Diversity Index vs. Points-Per-Game",
        "spearman_rho": float(rho) if len(team_season) >= 10 else None,
        "p_value": float(spearman_p) if len(team_season) >= 10 else None,
        "verdict": verdict_team if len(team_season) >= 10 else "NOT COMPUTED",
    },
    "individual_level": {
        "name": "Newcomer Performance OLS",
        "foreign_age_interaction_p": float(foreign_age_p) if foreign_age_p is not None else None,
        "foreign_signings_interaction_p": float(foreign_signings_p) if foreign_signings_p is not None else None,
        "verdict": verdict_ind,
    },
    "last_computed": datetime.now(timezone.utc).isoformat(),
}

with open("verdict_h4.json", "w") as f:
    json.dump(verdict_record, f, indent=2)