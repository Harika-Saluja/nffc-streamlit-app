# Access control & bucket etiquette

## Model (adopted)

- All project data is in **one bucket**: `nffcfirstteamstudents`.
- The cohort shares **one read+write key** (IT-issued). It is **not** read-only:
  every student can list, download, upload, overwrite, and delete.
- There is **no per-student isolation or audit trail** — protection is by
  **convention + a personal-folder layout**, not IAM permissions.
- Revocation is one action: IT rotates/deletes the key and the whole cohort
  loses access — appropriate for a fixed-term cohort that ends together.

## Why read+write (and the risk we accepted)

Students need to save features, models, and outputs back to the bucket, so a
read-only key was traded for a shared read+write key. **Accepted risk:** a
student can overwrite or delete shared data or a teammate's work, with no undo.
We mitigate with layout + tooling rather than permissions:

- **Personal folders.** Everyone writes under `students/<you>/`. The
  `nffc_data.upload_parquet` / `upload_file` helpers default there (driven by
  `WASABI_USER`), so the safe path is the easy path.
- **Shared data is read-only by convention.** Never write over the source
  datasets (`Statsbomb/`, `SecondSpectrum/`, `Catapult/`, `injuries/`).
- **Brief the students.** Make the overwrite risk explicit at kickoff — it's in
  the README and `docs/data_access.md`.

## Bucket layout

```
nffcfirstteamstudents/
├── Statsbomb/  SecondSpectrum/  Catapult/  injuries/   # shared — read-only by convention
└── students/
    ├── alice/ …     # personal workspaces — write here
    └── bob/   …
```

## Optional: real read-only enforcement (not currently used)

If you later want to remove the overwrite risk, ask IT for a **read-only**
student key (keeping a separate write key admin-only), or — with account root
keys — run `pipelines/setup_readonly_access.py`, which attaches:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ListBucket", "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::nffcfirstteamstudents" },
    { "Sid": "ReadObjects", "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::nffcfirstteamstudents/*" }
  ]
}
```

A hybrid that *keeps* personal writes is possible — allow `PutObject`/`DeleteObject`
only under `students/${aws:username}/*` and read elsewhere — but that needs
per-student IAM users, which we deliberately avoided for simplicity.

References: Wasabi
[sub-user + keys](https://docs.wasabi.com/docs/how-do-i-create-a-sub-user-with-console-access-and-access-and-secret-keys),
[policy](https://docs.wasabi.com/docs/creating-a-policy),
[IAM/STS](https://docs.wasabi.com/apidocs/iam-and-sts-support).

## Distribution & hygiene

- Share the key over a secure channel; students put it in `.env` (gitignored).
- Rotate the key at project end (IT) to revoke the whole cohort at once.
