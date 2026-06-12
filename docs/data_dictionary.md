# Data dictionary

All keys below are relative to the bucket `nffc-uob-msc-projects-2026`.
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

---

## Identity & linkage

A separate **identity mapping** CSV (NDA-covered, provided by the supervisor) ties:

| column | source |
|---|---|
| `player_name` | canonical name |
| `opta_id` | Opta / StatsBomb `player_id`, SecondSpectrum `optaId` |
| `tm_id` | Transfermarkt id → public injury datasets |
| `fpl_element_id` | FPL `id` → vaastav FPL archive |

Use it to join club datasets to each other and to the public injury archives
(`docs/external_data.md`). Helper: `nffc_data.external.link_via_mapping(...)`.
