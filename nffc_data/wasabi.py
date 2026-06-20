"""Access to the NFFC–UoB project datasets on Wasabi S3.

The project data lives in a single Wasabi bucket (default
``nffcfirstteamstudents``).

⚠️ **The whole cohort shares ONE read+write key.** That means:

* You can save your own work to the bucket — but writes are real and visible to
  everyone, and you *can* overwrite or delete shared data or a teammate's files.
* **Never write outside your personal folder.** Save your work under
  ``students/<you>/`` using :func:`upload_parquet` / :func:`upload_file` (which
  default there). Set ``WASABI_USER`` in your ``.env`` to your name/initials.
* **Never touch the shared source datasets** (``Statsbomb/``, ``SecondSpectrum/``,
  ``Catapult/``, ``injuries/``) — read them, don't overwrite them.

Typical use::

    import nffc_data as nffc

    nffc.list_bucket()                       # see what's in the bucket
    df = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
    nffc.upload_parquet(my_features, "features.parquet")   # -> students/<you>/features.parquet

Credentials are read from a ``.env`` file (see ``.env.example``) or the
environment: ``WASABI_ACCESS_KEY``, ``WASABI_SECRET_KEY``, and optionally
``WASABI_REGION``, ``WASABI_BUCKET`` and ``WASABI_USER``.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

import pandas as pd
import s3fs
from dotenv import load_dotenv

DEFAULT_BUCKET = "nffcfirstteamstudents"
DEFAULT_REGION = "eu-west-1"


def get_keys() -> tuple[str, str]:
    """Return ``(access_key, secret_key)`` from ``.env`` / the environment.

    Raises a clear error if either is missing so students get an actionable
    message instead of an opaque S3 permissions failure.
    """
    load_dotenv()
    access_key = os.getenv("WASABI_ACCESS_KEY")
    secret_key = os.getenv("WASABI_SECRET_KEY")
    if not access_key or not secret_key:
        raise RuntimeError(
            "Missing Wasabi credentials. Copy `.env.example` to `.env` and set "
            "WASABI_ACCESS_KEY and WASABI_SECRET_KEY to the key you were given."
        )
    return access_key, secret_key


def get_bucket(bucket: Optional[str] = None) -> str:
    """Return the bucket name (arg > ``WASABI_BUCKET`` env > default)."""
    load_dotenv()
    return bucket or os.getenv("WASABI_BUCKET") or DEFAULT_BUCKET


def get_region() -> str:
    load_dotenv()
    return os.getenv("WASABI_REGION") or DEFAULT_REGION


def _endpoint_url(region: str) -> str:
    # Wasabi's us-east-1 uses the short endpoint; other regions are regioned.
    if region == "us-east-1":
        return "https://s3.wasabisys.com"
    return f"https://s3.{region}.wasabisys.com"


@lru_cache(maxsize=1)
def get_fs() -> s3fs.S3FileSystem:
    """Return a cached ``s3fs`` filesystem pointed at Wasabi (shared read+write)."""
    access_key, secret_key = get_keys()
    region = get_region()
    return s3fs.S3FileSystem(
        key=access_key,
        secret=secret_key,
        client_kwargs={"endpoint_url": _endpoint_url(region)},
    )


def _full_path(key: str, bucket: Optional[str] = None) -> str:
    return f"{get_bucket(bucket)}/{key.lstrip('/')}"


def list_bucket(prefix: str = "", depth: int = 2, bucket: Optional[str] = None) -> dict:
    """Return a nested dict describing the bucket layout under ``prefix``.

    ``depth`` limits how many folder levels are expanded. Files at each level
    are listed under a ``"files"`` key. Handy for discovering what's available
    before you read it.
    """
    fs = get_fs()
    bucket = get_bucket(bucket)

    def build(path: str, level: int) -> dict:
        node: dict = {}
        try:
            entries = fs.ls(f"{bucket}/{path}".rstrip("/"), detail=True)
        except FileNotFoundError:
            return node
        for entry in entries:
            name = entry["Key"].rstrip("/").split("/")[-1]
            if entry.get("type") == "directory" or entry.get("StorageClass") == "DIRECTORY":
                if level < depth:
                    node[name] = build(f"{path}/{name}".strip("/"), level + 1)
                else:
                    node.setdefault("folders", []).append(name)
            else:
                node.setdefault("files", []).append(name)
        return node

    return build(prefix.strip("/"), 1)


def ls(prefix: str = "", bucket: Optional[str] = None) -> list[str]:
    """Return the immediate keys under ``prefix`` (one level, flat list)."""
    fs = get_fs()
    bucket = get_bucket(bucket)
    entries = fs.ls(f"{bucket}/{prefix}".rstrip("/"), detail=False)
    return [e.split(f"{bucket}/", 1)[-1] for e in entries]


def load_parquet(key: str, bucket: Optional[str] = None) -> pd.DataFrame:
    """Read a parquet object from the bucket into a DataFrame."""
    return pd.read_parquet(f"s3://{_full_path(key, bucket)}", filesystem=get_fs())


def read_json(key: str, bucket: Optional[str] = None) -> dict | list:
    """Read a JSON object from the bucket (e.g. a tracking metadata file)."""
    fs = get_fs()
    with fs.open(_full_path(key, bucket), "rb") as fh:
        return json.load(fh)


def read_jsonl(key: str, bucket: Optional[str] = None) -> pd.DataFrame:
    """Read a newline-delimited JSON object (e.g. tracking frames) into a DataFrame.

    Note: full SecondSpectrum tracking files are large (~400 MB / game). For
    big files prefer ``download_file`` + chunked reading, or the helpers in
    :mod:`nffc_data.ssio`.
    """
    fs = get_fs()
    rows = []
    with fs.open(_full_path(key, bucket), "rb") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def download_file(key: str, local_path: str, bucket: Optional[str] = None) -> str:
    """Download an object to ``local_path`` and return the path.

    Useful for large tracking files you want to work with locally.
    """
    fs = get_fs()
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    fs.get(_full_path(key, bucket), local_path)
    return local_path


# --------------------------------------------------------------------------- #
# Writing your own work back to the bucket
#
# ⚠️ Shared bucket, shared key. Writes are real and visible to everyone, and a
# write to the wrong key WILL overwrite shared data or a teammate's file with no
# undo. Keep your work under your personal folder (the default below).
# --------------------------------------------------------------------------- #
def get_user() -> str:
    """Your personal-folder name, from ``WASABI_USER`` in ``.env``."""
    load_dotenv()
    user = os.getenv("WASABI_USER") or os.getenv("NFFC_USER")
    if not user:
        raise RuntimeError(
            "Set WASABI_USER in your .env (your name or initials). Your work is "
            "saved under students/<WASABI_USER>/ so you don't overwrite shared "
            "data or a teammate's files."
        )
    return user


def personal_key(rel: str, user: Optional[str] = None) -> str:
    """Build a key inside your personal folder: ``students/<user>/<rel>``."""
    return f"students/{user or get_user()}/{rel.lstrip('/')}"


def upload_parquet(df, rel: str, *, personal: bool = True, user: Optional[str] = None,
                   bucket: Optional[str] = None) -> str:
    """Write a DataFrame as parquet to the bucket; returns the key written.

    Defaults to your personal folder (``students/<you>/<rel>``). Set
    ``personal=False`` to write an arbitrary ``rel`` key — only for agreed shared
    outputs, and NEVER over the source datasets (``Statsbomb/``, ``SecondSpectrum/``,
    ``Catapult/``, ``injuries/``).
    """
    key = personal_key(rel, user) if personal else rel.lstrip("/")
    df.to_parquet(f"s3://{_full_path(key, bucket)}", filesystem=get_fs(), index=False)
    return key


def upload_file(local_path: str, rel: str, *, personal: bool = True, user: Optional[str] = None,
                bucket: Optional[str] = None) -> str:
    """Upload a local file to the bucket; returns the key written.

    Defaults to your personal folder. See :func:`upload_parquet` for the
    ``personal=False`` caveat.
    """
    key = personal_key(rel, user) if personal else rel.lstrip("/")
    get_fs().put(local_path, _full_path(key, bucket))
    return key
