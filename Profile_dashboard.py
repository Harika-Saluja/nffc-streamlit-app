import gradio as gr
import duckdb
import pandas as pd

# ---------------------------------------------------------
# Load Parquet (lineups only for now)
# ---------------------------------------------------------
con = duckdb.connect()
con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
""")

# ---------------------------------------------------------
# Get player list
# ---------------------------------------------------------
players = con.execute("""
    SELECT DISTINCT player_name
    FROM lineups
    ORDER BY player_name
""").df()["player_name"].tolist()

# ---------------------------------------------------------
# Main function
# ---------------------------------------------------------
def player_profile(player_name):

    # -------------------------------
    # Fetch bio
    # -------------------------------
    bio = con.execute(f"""
        SELECT player_id, player_name, player_nickname, birth_date, player_gender,
               player_height, player_weight, jersey_number, country, formations
        FROM lineups
        WHERE player_name = '{player_name}'
        LIMIT 1
    """).df()

    if bio.empty:
        bio_left = pd.DataFrame({"Info": ["No bio available"]})
        bio_right = pd.DataFrame()
    else:
        # Split into two columns (left + right)
        bio_left = pd.DataFrame({
            "Field": ["Player ID", "Birth Date", "Gender", "Country"],
            "Value": [
                int(bio["player_id"].iloc[0]),
                bio["birth_date"].iloc[0],
                bio["player_gender"].iloc[0],
                bio["country"].iloc[0]
            ]
        })

        bio_right = pd.DataFrame({
            "Field": ["Height (cm)", "Weight (kg)", "Jersey Number"],
            "Value": [
                bio["player_height"].iloc[0],
                bio["player_weight"].iloc[0],
                bio["jersey_number"].iloc[0]
            ]
        })

    # -------------------------------
    # Performance Trend placeholder
    # -------------------------------
    perf_placeholder = "Graph will be added here."

    # -------------------------------
    # Verdict Summary placeholder
    # -------------------------------
    verdict_text = (
        "### Hypothesis 1: Adaptation Tax\n"
        "Result will be added here.\n\n"
        "### Hypothesis 2: Transfer Timing\n"
        "Result will be added here.\n\n"
        "### Hypothesis 3: Age Optimization\n"
        "Result will be added here.\n\n"
        "### Hypothesis 4: Squad Balance\n"
        "Result will be added here."
    )

    # -------------------------------
    # Perfect Signing Score placeholder
    # -------------------------------
    signing_score_placeholder = "Gauge chart will be added here."

    return (
        bio_left,
        bio_right,
        perf_placeholder,
        verdict_text,
        signing_score_placeholder
    )

# ---------------------------------------------------------
# Gradio UI Layout
# ---------------------------------------------------------
with gr.Blocks(title="Player Profile Dashboard") as demo:

    gr.Markdown("# Player Profile")

    with gr.Row():
        player_dropdown = gr.Dropdown(
            choices=players,
            label="Player Selector",
            value=players[0]
        )

    gr.Markdown("---")
    gr.Markdown("## Player Bio")

    with gr.Row():
        bio_left = gr.Dataframe(label="Basic Information")
        bio_right = gr.Dataframe(label="Physical & Squad Info")

    gr.Markdown("---")
    gr.Markdown("## Performance Trend")
    perf_section = gr.Markdown("*(Graph will be added here)*")

    gr.Markdown("---")
    gr.Markdown("## Verdict Summary")
    verdict_section = gr.Markdown("")

    gr.Markdown("---")
    gr.Markdown("## Perfect Signing Score")
    signing_score_section = gr.Markdown("*(Gauge chart will be added here)*")

    # Update function
    player_dropdown.change(
        fn=player_profile,
        inputs=player_dropdown,
        outputs=[bio_left, bio_right, perf_section, verdict_section, signing_score_section]
    )

demo.launch()
