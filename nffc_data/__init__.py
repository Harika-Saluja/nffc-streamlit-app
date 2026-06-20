"""nffc_data — access to the NFFC–UoB MSc project datasets on Wasabi S3.

Quick start::

    import nffc_data as nffc

    nffc.list_bucket()                    # what's in the bucket?
    df = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")
    nffc.upload_parquet(my_df, "out.parquet")   # -> students/<you>/out.parquet

Submodules:
    * :mod:`nffc_data.wasabi`    — bucket access: list/read/download + write to
      your personal folder (``upload_parquet``/``upload_file``).
    * :mod:`nffc_data.ssio`      — SecondSpectrum tracking readers.
    * :mod:`nffc_data.statsbomb` — StatsBomb matches/events/lineups loader.

⚠️ The cohort shares ONE read+write key. Save your work under ``students/<you>/``
(the ``upload_*`` helpers default there) and never overwrite the shared datasets
or a teammate's files — there is no undo. See ``docs/bucket_usage.md``.
"""

from . import ssio, statsbomb, wasabi
from .wasabi import (
    download_file,
    get_fs,
    list_bucket,
    load_parquet,
    ls,
    personal_key,
    read_json,
    read_jsonl,
    upload_file,
    upload_parquet,
)

__all__ = [
    "wasabi",
    "ssio",
    "statsbomb",
    "list_bucket",
    "ls",
    "load_parquet",
    "read_json",
    "read_jsonl",
    "download_file",
    "get_fs",
    "upload_parquet",
    "upload_file",
    "personal_key",
]
