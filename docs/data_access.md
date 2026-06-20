# Data access guide

All project data lives in a single Wasabi S3 bucket: **`nffcfirstteamstudents`**.
You access it with the Python package `nffc_data`. The whole cohort shares **one
read+write key** — see [Saving your work](#3-saving-your-work-shared-bucket) for
the etiquette that keeps everyone's data safe.

## 1. Set up

```bash
git clone https://github.com/seangroom82/NFFC-UoB-Projects.git
cd NFFC-UoB-Projects
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env`, paste the shared access key + secret you were given, and set
`WASABI_USER` to your name/initials (used for your personal folder):

```
WASABI_ACCESS_KEY=...
WASABI_SECRET_KEY=...
WASABI_REGION=eu-west-1
WASABI_BUCKET=nffcfirstteamstudents
WASABI_USER=your-name
```

`.env` is gitignored — **never commit it or paste keys into notebooks/code.**

## 2. First calls

```python
import nffc_data as nffc

# What's in the bucket?
nffc.list_bucket(depth=2)

# Flat listing of one prefix
nffc.ls("Statsbomb/Premier League/2023-2024")

# Read a parquet
matches = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")

# Read JSON / JSONL
meta = nffc.read_json("SecondSpectrum/202425/g2561895/g2561895_SecondSpectrum_Metadata.json")
```

Higher-level helpers: `nffc_data.statsbomb.StatsBombLoader`, `nffc_data.ssio`,
`nffc_data.external`. See `examples/` for runnable notebooks.

## 3. Saving your work (shared bucket)

The cohort shares **one read+write key**, so you can save work back to the
bucket — but a write is real, visible to everyone, and has **no undo**. To stay
safe, keep everything in **your personal folder** `students/<you>/`. The write
helpers default there once `WASABI_USER` is set:

```python
nffc.upload_parquet(my_features, "features.parquet")   # -> students/<you>/features.parquet
nffc.upload_file("model.pkl", "models/model.pkl")        # -> students/<you>/models/model.pkl
nffc.personal_key("features.parquet")                    # -> "students/<you>/features.parquet"
```

Rules:
- ✅ Read anything; write only under `students/<you>/`.
- 🚫 Never overwrite/delete the shared source datasets (`Statsbomb/`,
  `SecondSpectrum/`, `Catapult/`, `injuries/`) or another student's folder.
- Only pass `personal=False` to the `upload_*` helpers for outputs the group has
  explicitly agreed to share.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `RuntimeError: Missing Wasabi credentials` | `.env` not created or keys blank. Copy `.env.example` → `.env` and fill it in. |
| `RuntimeError: Set WASABI_USER` on upload | Add `WASABI_USER=your-name` to `.env` — uploads go to `students/<you>/`. |
| `AccessDenied` / `InvalidAccessKeyId` on read | Wrong key, or key not yet active. Re-check `.env`; ask supervisor to confirm the key. |
| `FileNotFoundError` for a key | Check the exact path with `nffc.list_bucket()` / `nffc.ls(prefix)` — S3 keys are case-sensitive and include spaces (e.g. `Premier League`). |
| `EndpointConnectionError` | Check `WASABI_REGION` (default `eu-west-1`). |
| Tracking read is slow / huge | SecondSpectrum games are ~400 MB. Use `nffc.download_file(...)` once, then `nffc_data.ssio.read_tracking_local(...)`. |
