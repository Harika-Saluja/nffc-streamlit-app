# Access control

## Model

- All student data is in **one dedicated bucket**: `nffc-uob-msc-projects-2026`.
- The cohort shares **one read-only access key**, scoped to this bucket only.
- Read-only is enforced at the **Wasabi IAM level** (not just convention): the
  key's policy grants `s3:GetObject` + `s3:ListBucket` and nothing else, so it
  physically cannot upload, overwrite, or delete.
- Revocation is one action — delete the key/user and the whole cohort loses
  access (appropriate for a fixed-term cohort that ends together).
- Trade-off accepted: a shared key means no per-student revocation or per-student
  audit trail.

## Read-only policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ListBucket", "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::nffc-uob-msc-projects-2026" },
    { "Sid": "ReadObjects", "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::nffc-uob-msc-projects-2026/*" }
  ]
}
```

(Add `s3:ListAllMyBuckets` only if students also need to browse in the Wasabi
web console; not needed for the Python API.)

## Option A — programmatic (recommended)

```bash
# pipelines/.env must have WASABI_ROOT_ACCESS_KEY / WASABI_ROOT_SECRET_KEY
python pipelines/setup_readonly_access.py          # prints the shared key once
python pipelines/setup_readonly_access.py --revoke # at project end
```

This uses the Wasabi IAM-compatible API (`https://iam.wasabisys.com`) to create
the sub-user `uob-msc-2026`, attach the policy above, and emit one access key.

## Option B — Wasabi console (manual)

1. **Users → Create User**, tick *Programmatic (create API key)*.
2. **Policies → Create Policy**, paste the JSON above.
3. Attach the policy to the user (or a group).
4. Copy the access key + secret (shown once) and distribute securely.

References: Wasabi
[create sub-user + keys](https://docs.wasabi.com/docs/how-do-i-create-a-sub-user-with-console-access-and-access-and-secret-keys),
[creating a policy](https://docs.wasabi.com/docs/creating-a-policy),
[IAM/STS support](https://docs.wasabi.com/apidocs/iam-and-sts-support).

## Distribution & hygiene

- Share the key over a secure channel; students put it in `.env` (gitignored).
- The `nffc_data` package ships **no write helpers**, reinforcing read-only use.
- Rotate/revoke at project end via `--revoke`.
