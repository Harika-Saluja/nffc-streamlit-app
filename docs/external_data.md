# External / public injury & availability data

The club datasets are **historic**, so injury and availability data is sourced
from **public archives that cover the same past seasons** — not scraped live.
You join them to the club data by player identity (see the mapping in
`docs/data_dictionary.md`). Helpers live in `nffc_data.external`.

> Do **not** scrape Transfermarkt directly — it is Cloudflare-protected and
> hostile to scraping. Use the pre-scraped datasets below, which republish it.

## 1. FPL archive — weekly minutes + a season-end availability snapshot

[`vaastav/Fantasy-Premier-League`](https://github.com/vaastav/Fantasy-Premier-League)
archives the official FPL API. **No auth.** Seasons **2016-17 → 2025-26**
(format `YYYY-YY`, e.g. `2023-24`). Get it via our helpers, `pandas.read_csv` on
the raw GitHub URL, or by cloning the repo (`data/{season}/...`).

```python
from nffc_data import external
players = external.load_fpl_players("2023-24")     # players_raw.csv  (snapshot)
gws     = external.load_fpl_gameweeks("2023-24")   # gws/merged_gw.csv (weekly)
```

Two files matter, with **different frequency** — read this carefully:

| File | Frequency | Key columns |
|---|---|---|
| `data/{season}/players_raw.csv` | **One row/player — season-END snapshot** (~865 rows) | identity: `id` (FPL element id), `first_name`, `second_name`, `web_name`, `team` (numeric → `teams.csv`), `element_type` (1 GK/2 DEF/3 MID/4 FWD). **availability:** `status` (`a` avail, `i` injured, `d` doubtful, `s` suspended, `u` unavailable), `news` (free text), `news_added`, `chance_of_playing_this_round`, `chance_of_playing_next_round` |
| `data/{season}/gws/merged_gw.csv` | **Per player per gameweek — WEEKLY** (~29.7k rows) | `name`, `element` (FPL id), `GW`, `kickoff_time`, `minutes`, `starts`, + performance stats |

> ⚠️ **Frequency caveat (important):** the `status`/`news`/`chance_of_playing`
> fields live **only in `players_raw.csv`, which is a single end-of-season
> snapshot** — they are **not** in `merged_gw.csv` or the per-GW files, so FPL
> does **not** give a weekly history of injury flags. What *is* weekly is
> **`minutes`**. Use it as a **proxy**: a run of consecutive 0-minute gameweeks
> after a player has been playing ≈ injured/unavailable (noisy — also catches
> rotation/bench). For clean **dated** injury spells, use Transfermarkt (§2) as
> the label source and FPL minutes for weekly corroboration + features.

Link FPL → club via `fpl_element_id` in the identity mapping (or by name/`team`).

## 2. Transfermarkt injury history (dated, typed injury spells)

**The injuries source is [salimt/football-datasets](https://github.com/salimt/football-datasets)**
→ `datalake/transfermarkt/player_injuries/player_injuries.csv` (public raw CSV,
no auth, ~8 MB). NOTE: dcaribou/transfermarkt-datasets and the Kaggle
`davidcariboo/player-scores` do **not** contain injuries — they're good for
transfers/valuations/appearances, but not this.

```python
from nffc_data import external
inj = external.load_transfermarkt_injuries()           # defaults to salimt player_injuries.csv
prof = external.load_transfermarkt_profiles()          # id -> name/DOB/position (for mapping + features)
# or point at your own download: external.load_transfermarkt_injuries("~/Downloads/injuries.csv")
```

`player_injuries.csv` — **event-based, one row per injury spell** (143k spells,
34.5k players; dates 1973 → Dec 2025; ~13.8k spells in 2023-24):

| Column | Meaning |
|---|---|
| `player_id` | **Transfermarkt id** → join to club data via `tm_id` |
| `season_name` | e.g. `23/24` |
| `injury_reason` | type / body part — **free text, messy** (`unknown injury`, `Hamstring injury`, `muscular problems`, …); normalise before use |
| `from_date`, `end_date` | spell start/end |
| `days_missed`, `games_missed` | duration |

`player_profiles.csv` (same repo) is the **`tm_id` → name mapping**: `player_id`
→ `player_name`, `player_slug`, `date_of_birth`, `position`/`main_position`,
`current_club_name`, height, foot. 92.7k players; covers 100% of the injury
players. Use it to build/verify the identity mapping and for static features.
Quirk: `player_name` has the id appended (`"Silvio Adzic (1)"`) — use
`player_slug` or strip the trailing ` (id)` for a clean name.

Caveats: `injury_reason` needs category normalisation (flag soft-tissue spells
for the injury project); it's a **static community snapshot** (last scrape
~Dec 2025), not auto-updated. Check the repo's licence; research use only.

## 3. Optional: premierinjuries.com (research licence)

[premierinjuries.com](https://www.premierinjuries.com/) holds every reported PL
injury since 2010 and **licenses data to research groups**. For deeper/cleaner
historical injury depth without scraping, the supervisor can request a research
data licence. Treat as supervisor-initiated.

## Joining recipe

```python
import nffc_data as nffc
from nffc_data import external
import pandas as pd

mapping = pd.read_csv("identity_mapping.csv")          # NDA-covered, supervisor-provided
events  = nffc.load_parquet("Statsbomb/Premier League/2023-2024/events/<match_id>.parquet")

# add Transfermarkt id, then join injuries
events = external.link_via_mapping(events, mapping,
                                   left_key="player_id", mapping_from="opta_id", mapping_to="tm_id")
inj = external.load_transfermarkt_injuries("injuries.csv")
joined = events.merge(inj, left_on="tm_id", right_on="player_id", how="left")
```

See `examples/05_injury_linkage.ipynb` for an end-to-end worked example.
