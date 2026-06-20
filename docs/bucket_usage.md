# Bucket usage & etiquette

## The shared key

The whole cohort shares **one access key** for the `nffcfirstteamstudents`
bucket. It has **read+write** access — you can save your own work to the bucket,
but you can also overwrite or delete shared data or a teammate's files, and
**there is no undo**. A little discipline keeps everyone's data safe.

## Bucket layout

```
nffcfirstteamstudents/
├── Statsbomb/  SecondSpectrum/  Catapult/  injuries/   # shared source data — read only
└── students/
    ├── alice/ …     # personal workspaces — write here
    └── bob/   …
```

## Rules

- ✅ **Read anything.**
- ✅ **Write only under your own folder** `students/<you>/`. Set `WASABI_USER` in
  your `.env` and the helpers put your work there automatically:
  ```python
  nffc.upload_parquet(my_features, "features.parquet")   # -> students/<you>/features.parquet
  nffc.upload_file("model.pkl", "models/model.pkl")        # -> students/<you>/models/model.pkl
  ```
- 🚫 **Never modify the shared source datasets** (`Statsbomb/`, `SecondSpectrum/`,
  `Catapult/`, `injuries/`) or another student's folder.
- 🚫 Only pass `personal=False` to the `upload_*` helpers for outputs the group
  has explicitly agreed to share.

If something shared looks wrong or got overwritten, tell the project maintainer —
don't try to "fix" it by writing over more data.
