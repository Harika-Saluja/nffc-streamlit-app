import os

base = r"C:\Users\harik\Desktop\MSC DSAI SEM 2\Company Project\NFFC-UoB-Projects"

for root, dirs, files in os.walk(base):
    for d in dirs:
        if d.lower() in ["events", "matches", "lineups"]:
            print("FOUND:", os.path.join(root, d))
