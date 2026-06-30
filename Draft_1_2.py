import nffc_data as nffc
import pandas as pd
import json
import pyarrow.dataset as ds

print("\n==============================")
print("1. CHECK STATSBOMB FEATURES")
print("==============================")

# --- Matches ---
matches_path = "Statsbomb/Premier League/2023-2024/matches.parquet"
matches = nffc.load_parquet(matches_path)
print("\n--- StatsBomb MATCHES Columns ---")
print(matches.columns.tolist())

# --- Events ---
events_prefix = "Statsbomb/Premier League/2023-2024/events"
event_files = nffc.ls(events_prefix)
sample_event = nffc.load_parquet(event_files[0])
print("\n--- StatsBomb EVENTS Columns ---")
print(sample_event.columns.tolist())

# --- Lineups ---
lineups_prefix = "Statsbomb/Premier League/2023-2024/lineups"
lineup_files = nffc.ls(lineups_prefix)
sample_lineup = nffc.read_json(lineup_files[0])

print("\n--- StatsBomb LINEUPS Keys ---")
print(sample_lineup.keys())

# Flatten lineup JSON to inspect all fields
lineup_rows = []
for team_name, players in sample_lineup.items():
    for p in players:
        lineup_rows.append(p)

lineups_df = pd.DataFrame(lineup_rows)
print("\n--- StatsBomb LINEUPS Flattened Columns ---")
print(lineups_df.columns.tolist())


print("\n==============================")
print("2. CHECK SECONDSPECTRUM FEATURES")
print("==============================")

# Pick one season and one game
season = "202425"
games = [k.rstrip("/").split("/")[-1] for k in nffc.ls(f"SecondSpectrum/{season}")]
game = games[0]

# Metadata
keys = nffc.ssio.game_files(season, game)
meta = nffc.ssio.read_metadata(keys["metadata"])

print("\n--- SecondSpectrum METADATA Keys ---")
print(meta.keys())

print("\n--- SecondSpectrum METADATA Home Players Sample ---")
print(meta["homePlayers"][:2])

# Tracking frames
frames = nffc.read_jsonl(keys["data"])
print("\n--- SecondSpectrum TRACKING Columns ---")
print(frames.columns.tolist())

print("\n--- SecondSpectrum TRACKING Sample Rows ---")
print(frames.head())


print("\n==============================")
print("3. CHECK CATAPULT FEATURES (CLEAN VERSION)")
print("==============================")

catapult_root = "Catapult/activity"
season_folders = nffc.ls(catapult_root)

all_catapult_columns = set()

for season_path in season_folders:
    print(f"\nSeason folder: {season_path}")

    # List date folders inside each season
    date_folders = nffc.ls(season_path)
    print(f"Found {len(date_folders)} date folders")

    for date_path in date_folders:
        # List files inside each date folder
        files = nffc.ls(date_path)

        for f in files:
            if f.endswith(".parquet"):
                df = nffc.load_parquet(f)

                # Collect columns only
                all_catapult_columns.update(df.columns.tolist())

# Print final combined column list
if all_catapult_columns:
    print("\n--- Combined Catapult Columns ---")
    print(sorted(all_catapult_columns))
else:
    print("No Catapult parquet files found.")


print("\n==============================")
print("4. CHECK INJURIES FEATURES")
print("==============================")

injuries_path = "injuries/gb1_injuries_with_mapping.parquet"
injuries_df = nffc.load_parquet(injuries_path)

print("\n--- Injuries Columns ---")
print(injuries_df.columns.tolist())


print("\n==============================")
print("FEATURE CHECK COMPLETE")
print("==============================")
