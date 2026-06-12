"""Loaders for *public* injury / availability archives, and identity-join helpers.

The club datasets are historic, so injury/availability data is sourced from
public archives that line up with past seasons (rather than scraped live):

* **vaastav/Fantasy-Premier-League** — the FPL API archived per season since
  2016/17. ``players_raw.csv`` carries availability fields (``status``,
  ``news``, ``news_added``, ``chance_of_playing_this_round/next_round``);
  ``gws/merged_gw.csv`` is the per-gameweek breakdown.
* **Pre-scraped Transfermarkt datasets** (e.g. dcaribou/transfermarkt-datasets,
  Kaggle ``davidcariboo/player-scores``) — injury type/dates/duration. Download
  one of these yourself and point :func:`load_transfermarkt_injuries` at it.

You join these to club data by *identity* using the project identity mapping
(player name ↔ optaId ↔ ``tm_id`` ↔ FPL ``element`` id). See
:func:`link_via_mapping`. The mapping CSV is provided separately (NDA-covered).
See ``docs/external_data.md`` for the full guide.
"""

from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import requests

VAASTAV_RAW = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"


def _fpl_season(season: str) -> str:
    """Normalise a season string to vaastav's ``YYYY-YY`` form.

    Accepts ``2023-2024``, ``2023-24``, or ``202324`` → ``2023-24``.
    """
    s = season.replace("/", "-")
    if "-" in s:
        start, end = s.split("-")
        return f"{start}-{end[-2:]}"
    if len(s) == 6:  # 202324
        return f"{s[:4]}-{s[-2:]}"
    return s


def _read_csv_url(url: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.content.decode("utf-8", errors="replace")))


def load_fpl_players(season: str) -> pd.DataFrame:
    """Load the season-end FPL player snapshot (``players_raw.csv``) from vaastav.

    Includes availability fields: ``status``, ``news``, ``news_added``,
    ``chance_of_playing_this_round``, ``chance_of_playing_next_round``, plus
    ``id`` (the FPL ``element`` id), ``first_name``, ``second_name``,
    ``web_name``, ``team``, ``element_type``.
    """
    url = f"{VAASTAV_RAW}/{_fpl_season(season)}/players_raw.csv"
    return _read_csv_url(url)


def load_fpl_gameweeks(season: str) -> pd.DataFrame:
    """Load the per-gameweek FPL data (``gws/merged_gw.csv``) from vaastav.

    Useful for tracking availability/news *over time* within a season.
    """
    url = f"{VAASTAV_RAW}/{_fpl_season(season)}/gws/merged_gw.csv"
    return _read_csv_url(url)


def load_transfermarkt_injuries(path: str) -> pd.DataFrame:
    """Load a pre-scraped Transfermarkt injuries CSV/parquet from a local path or URL.

    Download a dataset (e.g. the Kaggle ``davidcariboo/player-scores`` or
    dcaribou/transfermarkt-datasets ``injuries`` table) yourself and pass its
    path here. We don't redistribute these — see ``docs/external_data.md`` for
    links and licences.
    """
    if str(path).startswith(("http://", "https://")):
        return _read_csv_url(path)
    if str(path).endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path)


def link_via_mapping(
    df: pd.DataFrame,
    mapping: pd.DataFrame,
    left_key: str,
    mapping_from: str,
    mapping_to: str,
    new_col: Optional[str] = None,
) -> pd.DataFrame:
    """Add an external id to ``df`` by looking it up in the identity ``mapping``.

    E.g. to add a Transfermarkt id to a StatsBomb events frame keyed on
    ``player_id`` (optaId)::

        link_via_mapping(events, mapping,
                         left_key="player_id", mapping_from="opta_id",
                         mapping_to="tm_id")

    Returns a copy of ``df`` with ``mapping_to`` (or ``new_col``) joined on.
    """
    new_col = new_col or mapping_to
    lookup = mapping[[mapping_from, mapping_to]].drop_duplicates()
    merged = df.merge(
        lookup.rename(columns={mapping_from: left_key, mapping_to: new_col}),
        on=left_key,
        how="left",
    )
    return merged
