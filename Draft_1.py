import nffc_data as nffc
import pandas as pd
from pandas import json_normalize

print("\n=== BUCKET LISTING ===")
print(nffc.list_bucket(depth=2))

# ---------------------------------------------------------
# 1. LIST ALL FILES
# ---------------------------------------------------------
print("\n=== LINEUP FILES ===")
lineup_files = nffc.ls("Statsbomb/Premier League/2023-2024/lineups")
print(lineup_files)

print("\n=== EVENT FILES ===")
event_files = nffc.ls("Statsbomb/Premier League/2023-2024/events")
print(event_files[:10])  # show first 10 only

# ---------------------------------------------------------
# 2. LOAD MATCHES (single parquet file)
# ---------------------------------------------------------
print("\n=== LOADING MATCHES ===")
matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
print(matches.head())

# ---------------------------------------------------------
# 3. LOAD LINEUPS (correct extraction of nested JSON)
# ---------------------------------------------------------
print("\n=== LOADING LINEUPS ===")

lineup_rows = []

for f in lineup_files:
    if f.endswith(".parquet"):
        df = nffc.load_parquet(f)
        lineup_rows.append(df)

    elif f.endswith(".json") or f.endswith(".jsonl"):
        raw = nffc.read_json(f)

        for team_name, players in raw.items():
            for p in players:

                positions = p.get("positions", [])
                position = positions[0].get("position") if positions else None

                row = {
                    "match_id": f.split("/")[-1].replace(".json", ""),
                    "team": team_name,
                    "player_id": p.get("player_id"),
                    "player_name": p.get("player_name"),
                    "position": position,
                    "jersey_number": p.get("jersey_number")
                }
                lineup_rows.append(row)

lineups = pd.DataFrame(lineup_rows)
print(lineups.head())
print(lineups.columns.tolist())

# ---------------------------------------------------------
# 4. LOAD ONE SAMPLE EVENT FILE
# ---------------------------------------------------------
print("\n=== LOADING SAMPLE EVENT FILE ===")
sample_event = nffc.load_parquet(event_files[0])
print(sample_event.head())

# ---------------------------------------------------------
# 5. PRINT FEATURES (COLUMNS)
# ---------------------------------------------------------
print("\n=== MATCHES COLUMNS ===")
print(matches.columns.tolist())

print("\n=== LINEUPS COLUMNS ===")
print(lineups.columns.tolist())

print("\n=== EVENTS COLUMNS ===")
print(sample_event.columns.tolist())
