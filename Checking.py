import nffc_data as nffc
import pandas as pd
import json

# 1. Matches
matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
matches.to_parquet("matches.parquet", index=False)

# 2. Events
event_files = nffc.ls("Statsbomb/Premier League/2023-2024/events")
events = nffc.load_parquet(event_files[0])   # or loop all files if needed
events.to_parquet("events.parquet", index=False)

# 3. Lineups
lineup_files = nffc.ls("Statsbomb/Premier League/2023-2024/lineups")
lineup_json = nffc.read_json(lineup_files[0])

rows = []
for team, players in lineup_json.items():
    for p in players:
        rows.append(p)

lineups = pd.DataFrame(rows)

# Drop nested columns
nested_cols = ["stats", "events", "formations"]
lineups = lineups.drop(columns=[c for c in nested_cols if c in lineups.columns])

# Fix positions column
def flatten_positions(pos):
    if isinstance(pos, list):
        return ", ".join([str(x) for x in pos])
    if isinstance(pos, dict):
        return ", ".join([str(x) for x in pos.values()])
    if pos is None:
        return ""
    return str(pos)

lineups["positions"] = lineups["positions"].apply(flatten_positions)

# Drop any remaining nested columns
bad_cols = []
for col in lineups.columns:
    if lineups[col].apply(lambda x: isinstance(x, (list, dict))).any():
        bad_cols.append(col)

lineups = lineups.drop(columns=bad_cols)

lineups.to_parquet("lineups.parquet", index=False)
print("Lineups exported successfully!")



print("All raw datasets exported successfully!")
