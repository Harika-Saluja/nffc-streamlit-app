"""SecondSpectrum tracking I/O helpers (read-only).

These mirror the club's standard SecondSpectrum readers. Each Premier League
game is stored in the bucket as::

    SecondSpectrum/{season}/g{optaMatchId}/g{optaMatchId}_SecondSpectrum_Data.jsonl
    SecondSpectrum/{season}/g{optaMatchId}/g{optaMatchId}_SecondSpectrum_Metadata.json

The ``*_Data.jsonl`` file holds one JSON object per tracking frame (25 fps);
the ``*_Metadata.json`` file holds player/team identities (``optaId``,
``ssiId``, name, number, position), pitch dimensions and period definitions.
Join frames to identities via ``optaId`` / ``ssiId``.

Tracking files are large (~400 MB / game). To work offline, use
:func:`nffc_data.wasabi.download_file` to pull a game locally, then the
``*_local`` readers below.
"""

from __future__ import annotations

import json
import zipfile

import numpy as np
import pandas as pd

from . import wasabi


# --------------------------------------------------------------------------- #
# Read directly from the bucket (by object key)
# --------------------------------------------------------------------------- #
def read_metadata(key: str) -> dict:
    """Read a SecondSpectrum metadata JSON from the bucket."""
    return wasabi.read_json(key)


def read_tracking(key: str) -> pd.DataFrame:
    """Read a SecondSpectrum tracking ``.jsonl`` from the bucket into a DataFrame.

    Each row is one frame. Warning: this loads the whole file into memory
    (~400 MB/game). For repeated work, download once with
    :func:`nffc_data.wasabi.download_file` and use :func:`read_tracking_local`.
    """
    frames = wasabi.read_jsonl(key)
    if "frameIdx" in frames.columns:
        frames = frames.set_index("frameIdx", drop=False)
    return frames


def game_files(season: str, game_id: str) -> dict[str, str]:
    """Return the expected ``{data, metadata}`` object keys for a game.

    ``game_id`` may be given with or without the leading ``g`` (e.g. ``2444470``
    or ``g2444470``).
    """
    gid = game_id if str(game_id).startswith("g") else f"g{game_id}"
    base = f"SecondSpectrum/{season}/{gid}"
    return {
        "data": f"{base}/{gid}_SecondSpectrum_Data.jsonl",
        "metadata": f"{base}/{gid}_SecondSpectrum_Metadata.json",
    }


# --------------------------------------------------------------------------- #
# Read from local files (after downloading, or for a local .zip)
# --------------------------------------------------------------------------- #
def read_match_metadata_local(datadir: str, fname: str) -> dict:
    """Read a metadata JSON from a local directory or ``.zip``."""
    if datadir.endswith(".zip"):
        folder = datadir.split("/")[-1].replace(".zip", "")
        with zipfile.ZipFile(datadir, "r") as z:
            with z.open(folder + "/" + fname) as f:
                return json.load(f)
    with open(datadir + fname, "r") as f:
        return json.load(f)


def read_tracking_local(datadir: str, fname: str) -> pd.DataFrame:
    """Read a tracking ``.jsonl`` from a local directory or ``.zip``."""
    frames = []
    if datadir.endswith(".zip"):
        folder = datadir.split("/")[-1].replace(".zip", "")
        with zipfile.ZipFile(datadir, "r") as z:
            with z.open(folder + "/" + fname) as f:
                for line in f:
                    frames.append(json.loads(line))
    else:
        for line in open(datadir + fname, "r"):
            frames.append(json.loads(line))
    frames = pd.DataFrame(frames)
    if "frameIdx" in frames.columns:
        frames = frames.set_index("frameIdx", drop=False)
    return frames


def read_match_insight_local(datadir: str, fname: str) -> pd.DataFrame:
    """Read a SecondSpectrum insight ``.jsonl`` from a local directory or ``.zip``."""
    insight = []
    if datadir.endswith(".zip"):
        folder = datadir.split("/")[-1].replace(".zip", "")
        with zipfile.ZipFile(datadir, "r") as z:
            with z.open(folder + "/" + fname) as f:
                for line in f:
                    insight.append(json.loads(line))
    else:
        for line in open(datadir + fname, "r"):
            insight.append(json.loads(line))
    return pd.DataFrame(insight)


# --------------------------------------------------------------------------- #
# Analysis helpers
# --------------------------------------------------------------------------- #
def flip_positions(frames: pd.DataFrame, metadata: dict) -> None:
    """Normalise attacking direction so both teams attack the same way.

    Mutates the player/ball ``xyz`` lists in ``frames`` in place.
    """
    for _, row in frames.iterrows():
        home_attack_direction = metadata["periods"][row.period - 1]["homeAttPositive"]
        if ((home_attack_direction is True) and (row.lastTouch == "away")) or (
            (home_attack_direction is False) and (row.lastTouch == "home")
        ):
            for p in row.homePlayers:
                p["xyz"][0] *= -1
                p["xyz"][1] *= -1
            for p in row.awayPlayers:
                p["xyz"][0] *= -1
                p["xyz"][1] *= -1
            row.ball["xyz"][0] *= -1
            row.ball["xyz"][1] *= -1


def find_subs_opta_ids(insight: pd.DataFrame, metadata: dict) -> dict:
    """Return ``{'home': {off_id: on_id}, 'away': {...}}`` substitutions."""
    _ = insight[insight["optaEvent"].notna()]["optaEvent"].reset_index(drop=True)
    _ = _[(np.array([x["alignedFrameIdx"] for x in _]) != None)].reset_index(drop=True)  # noqa: E711
    aligned_frame_idx = np.array([x["alignedFrameIdx"] for x in _])
    ordered = _[np.argsort(aligned_frame_idx)]

    sub_on_events = [x for x in ordered if x["typeId"] == 19]
    sub_off_events = [x for x in ordered if x["typeId"] == 18]

    players_subbed = {"home": {}, "away": {}}
    for i in range(len(sub_on_events)):
        team = "home" if str(sub_on_events[i]["opContestantId"]) == metadata["homeOptaId"] else "away"
        players_subbed[team][sub_off_events[i]["opPlayerId"]] = sub_on_events[i]["opPlayerId"]
    return players_subbed
