"""nffc_data — read-only access to the NFFC–UoB MSc project datasets.

Quick start::

    import nffc_data as nffc

    nffc.list_bucket()                    # what's in the bucket?
    df = nffc.load_parquet("Statsbomb/Premier League/2023-2024/matches.parquet")

Submodules:
    * :mod:`nffc_data.wasabi`    — bucket access (list/read/download). No writes.
    * :mod:`nffc_data.ssio`      — SecondSpectrum tracking readers.
    * :mod:`nffc_data.statsbomb` — StatsBomb matches/events/lineups loader.
    * :mod:`nffc_data.external`  — public injury archives + identity-join helpers.

The access key is read-only and scoped to the project bucket: nothing here can
upload, overwrite, or delete data.
"""

from . import external, ssio, statsbomb, wasabi
from .wasabi import (
    download_file,
    get_fs,
    list_bucket,
    load_parquet,
    ls,
    read_json,
    read_jsonl,
)

__all__ = [
    "wasabi",
    "ssio",
    "statsbomb",
    "external",
    "list_bucket",
    "ls",
    "load_parquet",
    "read_json",
    "read_jsonl",
    "download_file",
    "get_fs",
]
