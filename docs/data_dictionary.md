# Data dictionary

All keys below are relative to the bucket `nffcfirstteamstudents`.
**Player identities are real** (NDA-covered) — no anonymisation. S3 keys are
case-sensitive and may contain spaces.

---

## 1. StatsBomb event data

```
Statsbomb/{league}/{season}/matches.parquet
Statsbomb/{league}/{season}/events/{match_id}.parquet
Statsbomb/{league}/{season}/lineups/{match_id}.json
```

- **Leagues:** Premier League, 1. Bundesliga, La Liga, Ligue 1, Serie A (top 5).
- **Seasons:** `2022-2023`, `2023-2024`, `2024-2025` (hyphenated).
- **Format:** parquet (matches/events) + JSON (lineups). Public open data — native player names.
- **Key columns (events):** `match_id`, `period`, `minute`, `second`, `type`, `team`, `player`, `player_id`, `position`, `location`, plus event-specific fields. See `docs/providers/Statsbomb/`.
- **Linkage:** join to other club data on `player_id` (Opta/StatsBomb id) via the identity mapping.
- **Loader:** `nffc_data.statsbomb.StatsBombLoader(league, season)`.

## 2. SecondSpectrum tracking (Premier League)

```
SecondSpectrum/{season}/g{optaMatchId}/g{optaMatchId}_SecondSpectrum_Data.jsonl
SecondSpectrum/{season}/g{optaMatchId}/g{optaMatchId}_SecondSpectrum_Metadata.json
```

- **Seasons:** `202324`, `202425` (complete, 380 games each), `202526` (partial).
- **`*_Data.jsonl`:** one JSON object per frame at **25 fps** (~400 MB/game). Per frame:
  `period`, `frameIdx`, `gameClock`, `wallClock`, `live`, `lastTouch`,
  `homePlayers`/`awayPlayers` (each `{playerId(ssiId), number, xyz:[x,y,z], speed, optaId}`),
  `ball` (`{xyz, speed}`).
- **`*_Metadata.json`:** `homePlayers`/`awayPlayers` (`name`, `number`, `position`, `ssiId`, `optaId`),
  `homeOptaId`/`awayOptaId`, `periods` (frame ranges + `homeAttPositive`), `pitchLength`, `pitchWidth`, `fps`.
- **Identities:** join frames ↔ metadata via `optaId` (preferred) or `ssiId`.
- **Loader:** `nffc_data.ssio` (`read_tracking`, `read_metadata`, `game_files`). For repeated work, `nffc.download_file` then `read_tracking_local`.

## 3. Catapult GPS (NFFC training — session/activity level)

```
Catapult/activity/season={YYYY-YYYY}/date={YYYY-MM-DD}/activity_{activity_id}.parquet
```

- One parquet per training **activity (session)**, all athletes combined.
- **Columns:** raw 10 Hz sensor fields (GPS/IMU) + `athlete_id`, `athlete_name` (real),
  `activity_id`, `activity_name`, `activity_start`. See `docs/providers/Catapult/`.
- **Granularity note:** this is **session-level**. The club's internal store uses a
  *different, intra-session per-period* layout — students should use only this
  `Catapult/activity/...` data. See `docs/ingestion_pipeline.md`.

## 4. Injuries + identity mapping (curated)

```
injuries/gb1_injuries_with_mapping.csv
injuries/gb1_injuries_with_mapping.parquet
```

- **Dated injury spells with the identity mapping already joined in** — 2,021
  spells across 667 players. This is the labels *and* the cross-id bridge in one file.
- **Columns:** `player_id` (Transfermarkt id), `player_name`, `statsbomb_id`,
  `second_spectrum_id` (null where no PL tracking match), `team_id`, `team_name`,
  `season` (e.g. `2024/2025`), `reason` (injury type), `from`, `until`,
  `days_missed`, `games_missed`.
- **Use:** the injury labels for Project 1; join to StatsBomb via `statsbomb_id`,
  to SecondSpectrum tracking via `second_spectrum_id`, and to public archives via
  `player_id` (= Transfermarkt `tm_id`) / FPL by name.

```python
import nffc_data as nffc
inj = nffc.load_parquet("injuries/gb1_injuries_with_mapping.parquet")
```

---

## Identity & linkage

For the curated injury players, the mapping is **already embedded** in
`injuries/gb1_injuries_with_mapping.*` (above): `player_id` (Transfermarkt) ↔
`statsbomb_id` ↔ `second_spectrum_id` ↔ `player_name`. Use those columns to join
injuries to the club datasets and to public archives:

| id column | links to |
|---|---|
| `statsbomb_id` | StatsBomb `player_id` (events/lineups) |
| `second_spectrum_id` | SecondSpectrum tracking player id (`ssiId`) |
| `player_id` (Transfermarkt) | public Transfermarkt datasets (`docs/external_data.md`) |
| `player_name` | FPL archive (by name/team), free-text matching |

For players outside this curated file, build out the mapping the same way (see
`docs/external_data.md`). Helper: `nffc_data.external.link_via_mapping(...)`.
