import nffc_data as nffc
import pandas as pd

# What's in the bucket?
print("Bucket Listing:")
print(nffc.list_bucket(depth=2))

# Flat listing of one prefix
print("\nPremier League Files")
print(nffc.ls("Statsbomb/Premier League/2023-2024"))

# Read a parquet
print("\nLoading matches parquet:")
matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
print(matches.head())

# Read JSON / JSONL
print("\nReading metadata:")
meta = nffc.read_json("SecondSpectrum/202425/g2444470/g2444470_SecondSpectrum_Metadata.json")
print(meta)

matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
#matches.to_excel("matches.xlsx", index=False)

# Load datasets
matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")

lineups = nffc.load_parquet_folder("Statsbomb/Premier League/2023-2024/lineups")
print(lineups.head())

# Print column names
print("MATCHES COLUMNS:")
print(matches.columns.tolist())

# Load one event file
event_files = nffc.ls("Statsbomb/Premier League/2023-2024/events")
sample = nffc.load_parquet(event_files[0])

print(sample.columns.tolist())
