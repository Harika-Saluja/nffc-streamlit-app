# NFFC–UoB MSc Projects

Data, code, and documentation for the Nottingham Forest × University of Birmingham
MSc research collaboration (2026 cohort, 6 projects).

This repo gives you access to club datasets on Wasabi S3, plus helpers, worked
examples, and guidance on linking to public injury data.

> ⚠️ **Confidential, NDA-covered data.** The datasets contain real player
> identities. By using this repo you agree to the data-usage rules below.
>
> ⚠️ **The whole cohort shares ONE read+write key.** You can save your own work
> to the bucket, but you can also overwrite or delete shared data or a teammate's
> files — there is no undo. **Only ever write under your own folder
> `students/<you>/`** (the `upload_*` helpers default there) and **never modify
> the shared source datasets.**

---

## Datasets

| Dataset | Description | Coverage | Format | Identity | Docs |
|---|---|---|---|---|---|
| **StatsBomb events** | Matches, events, lineups | Top-5 leagues, 2022-23 / 23-24 / 24-25 | parquet + json | native player names / `player_id` | [data dictionary](docs/data_dictionary.md) · [spec](docs/providers/Statsbomb/) |
| **SecondSpectrum tracking** | 25 fps player + ball tracking | Premier League, 202324 / 202425 (+partial 202526) | jsonl + json | `optaId`, names | [data dictionary](docs/data_dictionary.md) · [spec](docs/providers/SecondSpectrum/) |
| **Catapult GPS** | 10 Hz session (activity-level) GPS | NFFC training sessions | parquet | real `athlete_name`/`athlete_id` | [data dictionary](docs/data_dictionary.md) · [spec](docs/providers/Catapult/) |

Injury/availability data is **not** in the bucket — it comes from public archives
you join by player identity. See **[docs/external_data.md](docs/external_data.md)**.

## Quickstart

```bash
git clone https://github.com/seangroom82/NFFC-UoB-Projects.git
cd NFFC-UoB-Projects
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # paste in the shared key + set WASABI_USER to your name
```

```python
import nffc_data as nffc
nffc.list_bucket(depth=2)
matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
matches.head()
```

Then work through [`examples/`](examples/):

1. `01_quickstart_access.ipynb` — connect, list, read
2. `02_statsbomb_events.ipynb`
3. `03_secondspectrum_tracking.ipynb`
4. `04_catapult_gps.ipynb`
5. `05_injury_linkage.ipynb` — join club data to public injury archives

Full setup + troubleshooting: **[docs/data_access.md](docs/data_access.md)**.

## Your workspace (saving your work)

You share the bucket with the whole cohort, so keep your work in **your own
folder**, `students/<you>/`. Set `WASABI_USER` in your `.env`, then the write
helpers default there:

```python
nffc.upload_parquet(my_features, "features.parquet")   # -> students/<you>/features.parquet
nffc.upload_file("model.pkl", "models/model.pkl")       # -> students/<you>/models/model.pkl
key = nffc.personal_key("features.parquet")             # build the path yourself
```

**Rules of the shared bucket:**
- ✅ Read anything. Write **only** under `students/<you>/`.
- 🚫 Never overwrite/delete the shared source datasets (`Statsbomb/`,
  `SecondSpectrum/`, `Catapult/`, `injuries/`) or another student's folder.
- There is **no undo** — a wrong write clobbers the object permanently. The
  `upload_*` helpers default to your folder to keep you safe; only pass
  `personal=False` for outputs the group has explicitly agreed to share.

## Linking to public injury data

Because the club data is historic, use public archives that cover the same
seasons — the **FPL archive** (availability/news per gameweek) and **pre-scraped
Transfermarkt datasets** (injury type/dates) — joined by player identity. Helpers
in `nffc_data.external`; full guide in [docs/external_data.md](docs/external_data.md).

## Projects & research

- **[projects/](projects/README.md)** — the 6 project briefs (added as they're confirmed).
- **[papers/](papers/README.md)** — shared sports-analytics reading, indexed per project.

## Documentation

| Doc | Contents |
|---|---|
| [docs/data_access.md](docs/data_access.md) | Setup, first calls, troubleshooting |
| [docs/data_dictionary.md](docs/data_dictionary.md) | Bucket layout, schemas, identity & linkage |
| [docs/external_data.md](docs/external_data.md) | Public injury/availability sources + joining |
| [docs/ingestion_pipeline.md](docs/ingestion_pipeline.md) | How the data is produced (incl. GPS periodisation) |
| [docs/access_control_plan.md](docs/access_control_plan.md) | Shared key model & bucket etiquette |

## Data usage & NDA rules

- The data is **confidential** and covered by your signed NDA.
- **Real player identities** are present — handle accordingly.
- **Do not redistribute** data or commit it to public repos. The bucket data
  stays in the bucket; keep local copies private and delete them at project end.
- **Shared read+write key:** write only under `students/<you>/`; never modify the
  shared datasets or another student's folder. Writes have no undo.
- **Never commit credentials** — keys go in `.env` (gitignored) only.
- Publish results responsibly and per the collaboration agreement; check with
  the supervisor before sharing identifiable findings externally.
