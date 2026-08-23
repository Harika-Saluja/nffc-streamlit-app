import streamlit as st
import pandas as pd
import os
from datetime import datetime

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Data Manager", layout="wide")
st.title("DATA MANAGER")
st.caption(
    "Replace the data every dashboard uses — no Python required. Pick "
    "which type of dataset you're updating, upload a CSV or Excel file "
    "matching the required columns, and only the dashboards that "
    "actually use that dataset are affected. Everything else keeps "
    "using its current data."
)
st.warning(
    "**Important:** on Streamlit Cloud, uploads made here work "
    "immediately for anyone using the app right now, but the "
    "underlying files reset whenever the app reboots or redeploys. "
    "To make an update permanent, download the converted file after "
    "uploading (button appears below) and commit it into the "
    "`pages`-adjacent data folder in your GitHub repo, replacing the "
    "old one there."
)

# ===========================================================
# SCHEMA DEFINITIONS — one entry per dataset this app actually reads.
# `columns` lists every column required by AT LEAST ONE dashboard;
# `used_by` is shown to the user so they know the blast radius of an
# upload before they commit to it.
# ===========================================================
DATASET_SCHEMAS = {
    "Lineups": {
        "filename": "lineups.parquet",
        "used_by": ["Profile Dashboard", "League Adaptation", "Workload And Injury Risk",
                    "Age Optimization", "Squad Optimizer", "Myth Verdict"],
        "columns": {
            "player_id": "Whole number. Unique ID for each player.",
            "player_name": "Text. Player's display name.",
            "team_name": "Text. The team they played for in this match.",
            "country": "Text. Player's nationality (used for 'foreign' status in Squad Optimizer).",
            "birth_date": "Date, format YYYY-MM-DD. Used to compute age.",
            "primary_position": "Text, e.g. CB, RW, ST, CM, GK.",
            "minutes_played": "Whole number. Minutes played in this specific match.",
            "match_id": "Whole number. Must match an id in the Matches dataset.",
        },
        "example_rows": [
            {"player_id": 1, "player_name": "Jane Smith", "team_name": "City FC", "country": "England",
             "birth_date": "2001-04-12", "primary_position": "CM", "minutes_played": 90, "match_id": 101},
            {"player_id": 2, "player_name": "Ana Ruiz", "team_name": "City FC", "country": "Spain",
             "birth_date": "1999-11-03", "primary_position": "ST", "minutes_played": 75, "match_id": 101},
        ],
    },
    "Matches": {
        "filename": "matches.parquet",
        "used_by": ["Profile Dashboard", "League Adaptation", "Squad Optimizer", "Myth Verdict"],
        "columns": {
            "match_id": "Whole number. Unique ID for each match.",
            "season": "Text, e.g. '2024-25'.",
            "competition": "Text. League name, e.g. 'Premier League'.",
            "match_date": "Date, format YYYY-MM-DD.",
            "home_team": "Text.",
            "away_team": "Text.",
            "home_score": "Whole number.",
            "away_score": "Whole number.",
        },
        "example_rows": [
            {"match_id": 101, "season": "2024-25", "competition": "Premier League", "match_date": "2024-09-14",
             "home_team": "City FC", "away_team": "United FC", "home_score": 2, "away_score": 1},
        ],
    },
    "Events": {
        "filename": "events.parquet",
        "used_by": ["Profile Dashboard", "League Adaptation", "Squad Optimizer", "Myth Verdict"],
        "columns": {
            "match_id": "Whole number. Must match an id in the Matches dataset.",
            "player_id": "Whole number. Must match an id in the Lineups dataset.",
            "xg_sum": "Decimal number. Total Expected Goals for this player in this match.",
            "pass_success_mean": "Decimal number, 0 to 1. Average pass-success probability for this match.",
            "event_count": "Whole number. Total recorded on-ball events for this player in this match.",
        },
        "example_rows": [
            {"match_id": 101, "player_id": 1, "xg_sum": 0.24, "pass_success_mean": 0.82, "event_count": 58},
        ],
    },
    "Catapult (training load)": {
        "filename": "catapult.parquet",
        "used_by": ["Profile Dashboard", "Workload And Injury Risk", "Age Optimization", "Myth Verdict"],
        "columns": {
            "athlete_id": "Whole number. Catapult's own ID for the athlete — NOT the same as player_id, see Identity Crosswalk.",
            "date": "Date, format YYYY-MM-DD. The training session date.",
            "v_max": "Decimal number. Max speed recorded in the session.",
            "pl_sum": "Decimal number. Total player load for the session.",
            "a_sum": "Decimal number. Total acceleration load for the session.",
            "sl_sum": "Decimal number. Total sprint load for the session.",
            "hr_max": "Decimal number. Max heart rate recorded in the session.",
        },
        "example_rows": [
            {"athlete_id": 5001, "date": "2024-09-10", "v_max": 8.1, "pl_sum": 15234000,
             "a_sum": 17.2, "sl_sum": 21050, "hr_max": 188},
        ],
    },
    "Identity Crosswalk": {
        "filename": "identity_crosswalk.parquet",
        "used_by": ["Profile Dashboard", "Workload And Injury Risk", "Age Optimization", "Myth Verdict"],
        "columns": {
            "athlete_id": "Whole number. Must match an id in the Catapult dataset.",
            "statsbomb_player_id": "Whole number. Must match a player_id in the Lineups dataset.",
        },
        "example_rows": [
            {"athlete_id": 5001, "statsbomb_player_id": 1},
        ],
    },
    "Injuries": {
        "filename": "injuries.parquet",
        "used_by": ["Profile Dashboard", "Workload And Injury Risk"],
        "columns": {
            "statsbomb_id": "Whole number. Must match a player_id in the Lineups dataset.",
            "reason": "Text, e.g. 'Hamstring strain'.",
            "from": "Date, format YYYY-MM-DD. Injury start date.",
            "until": "Date, format YYYY-MM-DD. Injury end date.",
            "days_missed": "Whole number.",
            "games_missed": "Whole number.",
        },
        "example_rows": [
            {"statsbomb_id": 1, "reason": "Hamstring strain", "from": "2024-10-01",
             "until": "2024-10-22", "days_missed": 21, "games_missed": 3},
        ],
    },
}


# ===========================================================
# Pure functions (no Streamlit calls) — kept separate from the UI so
# they're directly testable.
# ===========================================================
def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    else:
        raise ValueError("Unsupported file type — please upload a .csv or .xlsx file.")


def validate_columns(df: pd.DataFrame, required_columns: list) -> tuple:
    """Returns (missing_columns, extra_columns) as sorted lists."""
    actual = set(df.columns)
    required = set(required_columns)
    missing = sorted(required - actual)
    extra = sorted(actual - required)
    return missing, extra


def dataset_status(filename: str) -> dict:
    if not os.path.exists(filename):
        return {"status": "⚪ Not uploaded yet", "rows": "—", "last_updated": "—"}
    try:
        df = pd.read_parquet(filename)
        mtime = datetime.fromtimestamp(os.path.getmtime(filename)).strftime("%Y-%m-%d %H:%M")
        return {"status": "🟢 Present", "rows": len(df), "last_updated": mtime}
    except Exception:
        return {"status": "🔴 Present but unreadable", "rows": "—", "last_updated": "—"}


# ===========================================================
# UI
# ===========================================================
st.header("1. Choose what kind of data you're uploading")
dataset_choice = st.selectbox("Dataset type:", list(DATASET_SCHEMAS.keys()))
schema = DATASET_SCHEMAS[dataset_choice]

st.info(
    f"**Used by:** {', '.join(schema['used_by'])}. Uploading a new "
    f"file here only affects these dashboards — every other dashboard "
    f"keeps using its current data."
)

st.markdown("---")
st.header("2. Download a template (recommended)")
example_df = pd.DataFrame(schema["example_rows"])
csv_bytes = example_df.to_csv(index=False).encode("utf-8")
st.download_button(
    f"Download {dataset_choice} template (CSV)", csv_bytes,
    file_name=f"{schema['filename'].replace('.parquet', '')}_template.csv", mime="text/csv",
)

with st.expander("ℹ️ Required columns for this dataset"):
    for col, desc in schema["columns"].items():
        st.markdown(f"- **{col}** — {desc}")

st.markdown("---")
st.header("3. Upload your file")
uploaded = st.file_uploader(f"{dataset_choice} — CSV or Excel file", type=["csv", "xlsx", "xls"], key=f"upload_{dataset_choice}")

if uploaded is not None:
    try:
        new_df = read_uploaded_file(uploaded)
    except Exception as e:
        st.error(f"Couldn't read that file: {e}")
        new_df = None

    if new_df is not None:
        required_cols = list(schema["columns"].keys())
        missing, extra = validate_columns(new_df, required_cols)

        if missing:
            st.error(
                f"Missing required column(s): {', '.join(missing)}. "
                f"Please add these (matching the exact names above) and re-upload."
            )
        else:
            if extra:
                st.warning(f"These extra column(s) will be ignored: {', '.join(extra)}.")
            st.success(f"Looks good — {len(new_df)} rows, all required columns present.")

            st.subheader("Preview (first 5 rows)")
            st.dataframe(new_df[required_cols].head(), width='stretch')

            col_confirm, col_download = st.columns(2)
            with col_confirm:
                if st.button(f"Confirm and replace {dataset_choice} data", type="primary"):
                    try:
                        new_df[required_cols].to_parquet(schema["filename"], index=False)
                        st.success(
                            f"{dataset_choice} data updated — "
                            f"{', '.join(schema['used_by'])} will now use this data."
                        )
                    except Exception as e:
                        st.error(f"Couldn't save the file: {e}")
            with col_download:
                parquet_bytes = new_df[required_cols].to_parquet(index=False)
                st.download_button(
                    "Download converted .parquet (to commit to GitHub for a permanent update)",
                    parquet_bytes, file_name=schema["filename"], mime="application/octet-stream",
                )

# ===========================================================
# CURRENT DATA STATUS
# ===========================================================
st.markdown("---")
st.header("Current Data Status")

status_rows = []
for name, s in DATASET_SCHEMAS.items():
    st_info = dataset_status(s["filename"])
    status_rows.append({
        "Dataset": name, "File": s["filename"], "Status": st_info["status"],
        "Rows": st_info["rows"], "Last Updated": st_info["last_updated"],
    })

st.dataframe(pd.DataFrame(status_rows), width='stretch', hide_index=True)