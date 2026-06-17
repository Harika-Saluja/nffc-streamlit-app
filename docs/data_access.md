# Data access guide

All project data lives in a single Wasabi S3 bucket: **`nffcfirstteamstudents`**.
You access it with the Python package `nffc_data` using a **read-only** key.

## 1. Set up

```bash
git clone https://github.com/seangroom82/NFFC-UoB-Projects.git
cd NFFC-UoB-Projects
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and paste the read-only access key + secret you were given:

```
WASABI_ACCESS_KEY=...
WASABI_SECRET_KEY=...
WASABI_REGION=eu-west-1
WASABI_BUCKET=nffcfirstteamstudents
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

## 3. Your key is read-only

The key can **list and download** only. It cannot upload, overwrite, or delete —
that's enforced at the Wasabi IAM level, not just by convention. If you need
something added to the bucket, ask the supervisor.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `RuntimeError: Missing Wasabi credentials` | `.env` not created or keys blank. Copy `.env.example` → `.env` and fill it in. |
| `AccessDenied` on a write/delete | Expected — the key is read-only. |
| `AccessDenied` / `InvalidAccessKeyId` on read | Wrong key, or key not yet active. Re-check `.env`; ask supervisor to confirm the key. |
| `FileNotFoundError` for a key | Check the exact path with `nffc.list_bucket()` / `nffc.ls(prefix)` — S3 keys are case-sensitive and include spaces (e.g. `Premier League`). |
| `EndpointConnectionError` | Check `WASABI_REGION` (default `eu-west-1`). |
| Tracking read is slow / huge | SecondSpectrum games are ~400 MB. Use `nffc.download_file(...)` once, then `nffc_data.ssio.read_tracking_local(...)`. |
