import pandas as pd
import os

base_path = r"C:\Users\harik\Desktop\MSC DSAI SEM 2\Company Project\NFFC-UoB-Projects\.venv\Lib\site-packages\botocore\data"

#Load all parquet files
def load_parquet_folder(folder_name):
    folder_path = os.path.join(base_path, folder_name)
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".parquet")]
    df_list = [pd.read_parquet(f) for f in files]
    return pd.concat(df_list, ignore_index = True)

events = load_parquet_folder("events")
matches = load_parquet_folder("matches")
lineups = load_parquet_folder("lineups")

print("\n Events Features:")
print(events.columns.to_list())

print("\n Matches Features:")
print(matches.columns.to_list())

print("\n Lineups Features:")
print(lineups.columns.to_list())