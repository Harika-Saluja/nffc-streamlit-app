"""Read-only loader for StatsBomb event data stored in the project bucket.

Layout in the bucket::

    Statsbomb/{league}/{season}/matches.parquet
    Statsbomb/{league}/{season}/events/{match_id}.parquet
    Statsbomb/{league}/{season}/lineups/{match_id}.json

``season`` uses hyphens (e.g. ``2023-2024``). Player names are native to
StatsBomb (public open data), so no identity mapping is needed for StatsBomb
itself — but the ``player``/``player_id`` columns let you join to the rest of
the club data via the project identity mapping.

Example::

    from nffc_data.statsbomb import StatsBombLoader

    sb = StatsBombLoader("Premier League", "2023-2024")
    matches = sb.load_matches()
    events = sb.load_events_for_match(matches.iloc[0]["match_id"])
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd
from tqdm import tqdm

from . import wasabi

DEFAULT_PREFIX = "Statsbomb"


class StatsBombLoader:
    """Loads StatsBomb matches/events/lineups from the Wasabi bucket.

    Set ``cache_dir`` to keep a local copy of anything you read (downloads are
    written there and reused on the next call).
    """

    def __init__(
        self,
        league: str,
        season: str,
        prefix: str = DEFAULT_PREFIX,
        cache_dir: Optional[str] = None,
        bucket: Optional[str] = None,
    ) -> None:
        self.league = league
        self.season = season.replace("/", "-")
        self.prefix = prefix.strip("/")
        self.bucket = wasabi.get_bucket(bucket)
        self.fs = wasabi.get_fs()

        self.cache_dir = Path(cache_dir) / league / self.season if cache_dir else None
        if self.cache_dir:
            (self.cache_dir / "events").mkdir(parents=True, exist_ok=True)
            (self.cache_dir / "lineups").mkdir(parents=True, exist_ok=True)

    # -- key/path helpers --------------------------------------------------- #
    def _key(self, *parts: str) -> str:
        return "/".join([self.prefix, self.league, self.season, *parts])

    def _cache(self, *parts: str) -> Optional[Path]:
        return self.cache_dir.joinpath(*parts) if self.cache_dir else None

    def _read_parquet(self, key: str, cache: Optional[Path]) -> Optional[pd.DataFrame]:
        if cache and cache.exists():
            return pd.read_parquet(cache)
        try:
            df = pd.read_parquet(f"s3://{self.bucket}/{key}", filesystem=self.fs)
        except (FileNotFoundError, OSError):
            return None
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)
        return df

    def _read_json(self, key: str, cache: Optional[Path]) -> Optional[dict]:
        if cache and cache.exists():
            with open(cache) as fh:
                return json.load(fh)
        try:
            with self.fs.open(f"{self.bucket}/{key}", "rb") as fh:
                data = json.load(fh)
        except (FileNotFoundError, OSError):
            return None
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            with open(cache, "w") as fh:
                json.dump(data, fh)
        return data

    # -- public API --------------------------------------------------------- #
    def load_matches(self, team: Optional[str] = None, matchweek_max: Optional[int] = None) -> pd.DataFrame:
        df = self._read_parquet(self._key("matches.parquet"), self._cache("matches.parquet"))
        if df is None:
            raise FileNotFoundError(f"No matches.parquet for {self.league} {self.season} in s3://{self.bucket}")
        if team:
            df = df[(df["home_team"] == team) | (df["away_team"] == team)]
        if matchweek_max:
            df = df[df["match_week"] <= matchweek_max]
        return df.reset_index(drop=True)

    def load_events_for_match(self, match_id: int, silent: bool = True) -> pd.DataFrame:
        df = self._read_parquet(self._key("events", f"{match_id}.parquet"), self._cache("events", f"{match_id}.parquet"))
        if df is None:
            if silent:
                return pd.DataFrame()
            raise FileNotFoundError(f"No events for match_id {match_id}")
        return df

    def load_lineups_for_match(self, match_id: int, silent: bool = True) -> dict:
        data = self._read_json(self._key("lineups", f"{match_id}.json"), self._cache("lineups", f"{match_id}.json"))
        if data is None:
            if silent:
                return {}
            raise FileNotFoundError(f"No lineups for match_id {match_id}")
        return data

    def load_events(self, team: Optional[str] = None, matchweek_max: Optional[int] = None) -> pd.DataFrame:
        """Load and concatenate events for all matches (optionally filtered)."""
        matches = self.load_matches(team=team, matchweek_max=matchweek_max)
        dfs = []
        for mid in tqdm(matches["match_id"], desc=f"{self.league} {self.season} events"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                dfs.append(self.load_events_for_match(mid))
        return pd.concat([d for d in dfs if not d.empty], ignore_index=True)
