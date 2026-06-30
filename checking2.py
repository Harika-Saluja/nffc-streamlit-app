import nffc_data as nffc
import pandas as pd
import json


# 2. Events
event_files = nffc.ls("Statsbomb/Premier League/2023-2024/events")
events = nffc.load_parquet(event_files[0])   # or loop all files if needed
events.to_parquet("events.parquet", index=False)