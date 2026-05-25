"""Day-in-the-life regression test.

Locks in the (profile_angle, winter_target, summer_target) outputs of
`solar.py` for a representative day of sun positions, at the maintainer's
default geometry. The point isn't astronomical accuracy — the (elevation,
azimuth) inputs are static fixtures, not derived from `astral` — but the
output snapshot guards against accidental algorithm drift.

How it works
------------
- First run (or when `tests/snapshots/baseline.json` is missing): the test
  generates the snapshot, writes it, and skips with a message asking you to
  review and commit.
- Subsequent runs: the test regenerates outputs and asserts deep-equal to
  the stored snapshot. Any drift fails with a clear diff.
- ``UPDATE_SNAPSHOT=1 pytest tests/test_baseline_snapshot.py`` rewrites the
  snapshot intentionally (for legitimate algorithm changes — the diff is the
  review surface).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Same import shim as test_solar.py — import solar.py standalone, no HA needed.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "custom_components" / "pergola_bioclimatique"),
)
from solar import (  # noqa: E402
    compute_profile_angle,
    compute_summer_target,
    compute_winter_target,
)


SNAPSHOT_PATH = Path(__file__).resolve().parent / "snapshots" / "baseline.json"


# Default geometry. Frozen here so future const.py edits don't silently change
# the snapshot — if these defaults move, that's a deliberate behavior change
# and the snapshot should be updated explicitly.
_DEFAULTS = {
    "face_azimuth": 130,
    "max_opening_angle": 135,
    "calibration_offset": -10,
    "blade_pitch_ratio": 0.92,
    "flip_profile_threshold": 80,
    "summer_blade_offset": 0,
    "phase_a_intercept": 40,
    "step_size": 5,
}


# Representative sun positions at the maintainer's latitude/longitude
# (~southern France) for a summer day (around June 21) and a winter day
# (around December 21). Hand-curated; physically plausible but not exact.
# Each entry is ``(local_hour_label, sun_elevation_deg, sun_azimuth_deg)``.
_SUMMER_DAY_POSITIONS: list[tuple[str, float, float]] = [
    ("06:00", 5.0, 65.0),
    ("07:00", 15.0, 75.0),
    ("08:00", 26.0, 85.0),
    ("09:00", 37.0, 96.0),
    ("10:00", 48.0, 110.0),
    ("11:00", 58.0, 130.0),
    ("12:00", 65.0, 160.0),
    ("13:00", 68.0, 195.0),  # solar noon-ish (just past)
    ("14:00", 64.0, 225.0),
    ("15:00", 55.0, 245.0),
    ("16:00", 44.0, 260.0),
    ("17:00", 33.0, 272.0),
    ("18:00", 22.0, 283.0),
    ("19:00", 11.0, 293.0),
    ("20:00", 2.0, 302.0),
]

_WINTER_DAY_POSITIONS: list[tuple[str, float, float]] = [
    ("08:00", 3.0, 122.0),
    ("09:00", 11.0, 135.0),
    ("10:00", 18.0, 150.0),
    ("11:00", 22.0, 168.0),
    ("12:00", 25.0, 187.0),
    ("13:00", 25.0, 207.0),  # solar noon ≈ winter peak
    ("14:00", 22.0, 225.0),
    ("15:00", 17.0, 240.0),
    ("16:00", 9.0, 254.0),
    ("17:00", 1.0, 266.0),
]


def _generate_snapshot() -> dict:
    """Compute the full output grid from current `solar.py` code."""
    snapshot: dict = {
        "defaults": _DEFAULTS,
        "summer_day": [],
        "winter_day": [],
    }
    for label, day_positions in (
        ("summer_day", _SUMMER_DAY_POSITIONS),
        ("winter_day", _WINTER_DAY_POSITIONS),
    ):
        # Winter mode tracks the highest target reached; emulate that
        # across the day so the snapshot reflects realistic behavior.
        winter_hold = 0.0
        for hour_label, elev, azim in day_positions:
            profile = compute_profile_angle(elev, azim, _DEFAULTS["face_azimuth"])
            winter = compute_winter_target(
                profile,
                _DEFAULTS["calibration_offset"],
                winter_hold,
                _DEFAULTS["max_opening_angle"],
                _DEFAULTS["step_size"],
            )
            winter_hold = winter  # propagate the hold for the next tick
            summer = compute_summer_target(
                profile,
                _DEFAULTS["calibration_offset"],
                _DEFAULTS["max_opening_angle"],
                _DEFAULTS["step_size"],
                _DEFAULTS["blade_pitch_ratio"],
                _DEFAULTS["flip_profile_threshold"],
                _DEFAULTS["summer_blade_offset"],
                _DEFAULTS["phase_a_intercept"],
            )
            snapshot[label].append({
                "hour": hour_label,
                "elevation": elev,
                "azimuth": azim,
                "profile_angle": round(profile, 4),
                "winter_target": round(winter, 4),
                "summer_target": round(summer, 4),
            })
    return snapshot


def _write_snapshot(data: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text())


def test_baseline_snapshot() -> None:
    """Lock in the day-in-the-life algorithm outputs."""
    current = _generate_snapshot()

    if os.environ.get("UPDATE_SNAPSHOT") == "1":
        _write_snapshot(current)
        pytest.skip(
            "Snapshot rewritten via UPDATE_SNAPSHOT=1 — review the diff in "
            f"{SNAPSHOT_PATH.relative_to(Path.cwd())} and commit."
        )

    if not SNAPSHOT_PATH.exists():
        _write_snapshot(current)
        pytest.skip(
            f"Snapshot bootstrapped at {SNAPSHOT_PATH.relative_to(Path.cwd())} — "
            "review the contents, commit, and re-run."
        )

    stored = _load_snapshot()
    assert stored == current, (
        "Algorithm output drifted from the locked-in snapshot. If this change "
        "is intentional, re-run with UPDATE_SNAPSHOT=1 and commit the diff."
    )
