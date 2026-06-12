# External / public injury & availability data

The club datasets are **historic**, so injury and availability data is sourced
from **public archives that cover the same past seasons** — not scraped live.
You join them to the club data by player identity (see the mapping in
`docs/data_dictionary.md`). Helpers live in `nffc_data.external`.

> Do **not** scrape Transfermarkt directly — it is Cloudflare-protected and
> hostile to scraping. Use the pre-scraped datasets below, which republish it.

## 1. FPL archive — availability/news per gameweek (recommended primary)

[`vaastav/Fantasy-Premier-League`](https://github.com/vaastav/Fantasy-Premier-League)
archives the official FPL API every season since 2016/17.

- **`players_raw.csv`** (season snapshot): `status`, `news`, `news_added`,
  `chance_of_playing_this_round`, `chance_of_playing_next_round`, `id`
  (FPL `element` id), `first_name`, `second_name`, `web_name`, `team`, `element_type`.
- **`gws/merged_gw.csv`**: per-gameweek rows — track availability/news over time.

```python
from nffc_data import external
players = external.load_fpl_players("2023-2024")     # season-end availability snapshot
gws     = external.load_fpl_gameweeks("2023-2024")   # per-gameweek detail
```

Link FPL → club via `fpl_element_id` in the identity mapping (or by name/team).

## 2. Transfermarkt injury history (depth: type, dates, duration)

Use a pre-scraped, republished dataset and point the loader at your download:

- [dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) — weekly-updated; has an `injuries` table.
- [Kaggle: davidcariboo/player-scores](https://www.kaggle.com/datasets/davidcariboo/player-scores) — Transfermarkt datalake incl. injuries.
- [salimt/football-datasets](https://github.com/salimt/football-datasets) — 93k+ players incl. injury records.

```python
inj = external.load_transfermarkt_injuries("~/Downloads/injuries.csv")  # local file or URL
```

Link Transfermarkt → club via `tm_id` in the identity mapping. Check each
dataset's licence before redistribution; download for research use only.

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
