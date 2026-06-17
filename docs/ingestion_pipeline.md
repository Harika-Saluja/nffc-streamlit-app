# How the data gets into the bucket (ingestion)

This is descriptive — students don't run these. The upload scripts live in the
private, gitignored `pipelines/` directory and require write credentials. The
bucket is populated from data the club already holds.

## Overview

```
StatsBomb API ──(create_season_sb_events.py)──► local cache ──(upload_statsbomb.py)──┐
SecondSpectrum DVMS ──(tracking_download.py)──► local tracking_data ──(upload_tracking.py)──┼─► nffcfirstteamstudents
Catapult Connect API ──────────(ingest_gps_activity.py)─────────────────────────────┘
```

All three retain **real identities** (NDA-covered). No anonymisation step.

## 1. StatsBomb

Events/matches/lineups are cached locally by the set-piece reporting project
(`create_season_sb_events.py`, using `statsbombpy`), then uploaded verbatim to
`Statsbomb/{league}/{season}/...`. Public open data, so nothing is stripped.
`upload_statsbomb.py` runs a completeness check (event files vs expected match
counts) before uploading and skips files already present.

## 2. SecondSpectrum tracking

Per-game files are downloaded from the Premier League **DVMS** API
(`tracking_download.py`) into `tracking_data/{season}/g{optaMatchId}/`, then
uploaded verbatim (`*_Data.jsonl` + `*_Metadata.json`) to
`SecondSpectrum/{season}/g{optaMatchId}/...`. Identities (`optaId`, names) are
already present in the files. Large (~400 MB/game, ~160 GB/season) → multipart
upload, skip-existing.

## 3. Catapult GPS — and the periodisation gotcha ⚠️

There are **two different periodisations** of the same GPS data, and this is a
common source of confusion:

| | Internal bucket `nffcfootballintelligence` | Student bucket `nffcfirstteamstudents` |
|---|---|---|
| Endpoint | `/periods/{id}/athletes/{id}/sensor` | `/activities/{id}/athletes/{id}/sensor` |
| Granularity | **Intra-session** — one file *per period* (warm-up, 1st half, …) | **Session-level** — one file *per activity (session)* |
| Layout | `date=.../period_<uuid>.parquet` | `Catapult/activity/season=.../date=.../activity_{id}.parquet` |
| Shared with students? | **No** | Yes |

Students get the **session-level (activity)** data, produced by
`ingest_gps_activity.py`. It fetches 10 Hz sensor data per athlete per activity,
filters to the NFFC team and excludes goalkeepers and rehab/extras periods,
keeps real `athlete_name`/`athlete_id`, and writes one parquet per activity.

**Do not point students at `nffcfootballintelligence`** — different granularity,
internal-only.

## Access keys

`pipelines/setup_readonly_access.py` mints the single shared read-only key the
students use. See `docs/access_control_plan.md`.
