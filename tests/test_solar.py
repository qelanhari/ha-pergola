"""Tests for solar geometry functions."""

import math
import sys
from pathlib import Path

import pytest

# Import solar module directly to avoid homeassistant dependency
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "pergola_bioclimatique")
)
from solar import (  # noqa: E402
    angle_to_percent,
    compute_profile_angle,
    compute_pv_threshold,
    compute_summer_target,
    compute_winter_target,
    quantize,
    smooth_pv,
)


class TestComputeProfileAngle:
    def test_sun_directly_on_face(self) -> None:
        """Sun at face azimuth, 45° elevation -> profile angle = 45°."""
        result = compute_profile_angle(45, 130, 130)
        assert abs(result - 45.0) < 0.1

    def test_sun_behind_pergola(self) -> None:
        """Delta azimuth >= 180 -> returns 0."""
        result = compute_profile_angle(45, 310, 130)
        assert result == 0.0

    def test_sun_at_horizon(self) -> None:
        """Elevation 0 -> profile angle 0."""
        result = compute_profile_angle(0, 130, 130)
        assert abs(result) < 0.1

    def test_sun_at_90_delta(self) -> None:
        """Delta azimuth = 90° -> cos(90°) ≈ 0 -> returns 90."""
        result = compute_profile_angle(45, 220, 130)
        assert abs(result - 90.0) < 0.5

    def test_high_elevation(self) -> None:
        """High elevation, small delta -> high profile angle."""
        result = compute_profile_angle(70, 140, 130)
        assert result > 60

    def test_negative_angle_wraps(self) -> None:
        """Negative atan result gets +180."""
        result = compute_profile_angle(-10, 130, 130)
        assert result >= 0

    def test_symmetric_delta(self) -> None:
        """Same delta on both sides should give same profile angle."""
        left = compute_profile_angle(40, 110, 130)
        right = compute_profile_angle(40, 150, 130)
        assert abs(left - right) < 0.1


class TestComputeWinterTarget:
    def test_follows_sun(self) -> None:
        result = compute_winter_target(
            profile_angle=60, calibration_offset=-10, current_pos=30,
            max_opening_angle=135, step_size=5,
        )
        expected_raw = (50 / 135) * 100  # ~37%
        assert result >= 35  # quantized to 35 or 40

    def test_holds_maximum(self) -> None:
        """Winter mode never goes below current position."""
        result = compute_winter_target(
            profile_angle=30, calibration_offset=-10, current_pos=50,
            max_opening_angle=135, step_size=5,
        )
        assert result >= 50

    def test_zero_angle(self) -> None:
        result = compute_winter_target(
            profile_angle=0, calibration_offset=-10, current_pos=0,
            max_opening_angle=135, step_size=5,
        )
        assert result == 0


class TestComputeSummerTarget:
    def test_normal_case(self) -> None:
        result = compute_summer_target(
            profile_angle=40, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        assert 0 <= result <= 100

    def test_clamp_to_100_when_side_b_negative(self) -> None:
        """Side A > max and side B ≤ 0 → stay at 100%."""
        result = compute_summer_target(
            profile_angle=80, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        # side_a = 170 > 135, side_b = 80-90-10 = -20 ≤ 0 → 100%
        assert result == 100.0

    def test_flip_to_side_b_when_viable(self) -> None:
        """Side A > max and side B > 0 → flip to side B."""
        result = compute_summer_target(
            profile_angle=120, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        # side_a = 210 > 135, side_b = 120-90-10 = 20 > 0
        # percent = 20/135*100 = 14.8% → quantize to 15%
        assert result == 15.0

    def test_flip_higher_profile(self) -> None:
        """Late afternoon, high profile angle → side B gives open position."""
        result = compute_summer_target(
            profile_angle=150, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        # side_b = 150-90-10 = 50 → 50/135*100 = 37% → 35%
        assert result == 35.0

    def test_midday_high_sun(self) -> None:
        """Profile angle 61° (sun high and facing) → should be 100%."""
        result = compute_summer_target(
            profile_angle=61, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        # s_raw = 61 + 90 - 10 + 10 = 151 > 135 -> 100%
        assert result == 100.0

    def test_low_profile_angle(self) -> None:
        result = compute_summer_target(
            profile_angle=20, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        # s_raw = 20 + 90 - 10 + 10 = 110 <= 135
        expected = quantize(angle_to_percent(110, 135), 5)
        assert abs(result - expected) < 5


class TestComputePvThreshold:
    def test_returns_at_least_400(self) -> None:
        result = compute_pv_threshold(130, 5, 130, 3000, 0.30)
        assert result >= 400

    def test_high_sun_high_threshold(self) -> None:
        result = compute_pv_threshold(130, 60, 130, 3000, 0.30)
        assert result > 400

    def test_sun_behind_low_threshold(self) -> None:
        result = compute_pv_threshold(310, 30, 130, 3000, 0.30)
        assert result == 400  # cos_aoi near 0, falls to min


class TestSmoothPv:
    def test_first_reading(self) -> None:
        result = smooth_pv(1000, 0, 0.4)
        assert result == 400.0

    def test_stable_reading(self) -> None:
        result = smooth_pv(500, 500, 0.4)
        assert result == 500.0

    def test_smoothing_dampens(self) -> None:
        result = smooth_pv(1000, 500, 0.4)
        assert 500 < result < 1000


class TestQuantize:
    def test_round_to_5(self) -> None:
        assert quantize(37, 5) == 35
        assert quantize(38, 5) == 40

    def test_clamp_below_zero(self) -> None:
        assert quantize(-10, 5) == 0

    def test_clamp_above_100(self) -> None:
        assert quantize(110, 5) == 100

    def test_exact_multiple(self) -> None:
        assert quantize(50, 5) == 50

    def test_step_10(self) -> None:
        assert quantize(27, 10) == 30
        assert quantize(24, 10) == 20


class TestAngleToPercent:
    def test_zero(self) -> None:
        assert angle_to_percent(0, 135) == 0

    def test_max(self) -> None:
        assert abs(angle_to_percent(135, 135) - 100) < 0.1

    def test_half(self) -> None:
        result = angle_to_percent(67.5, 135)
        assert abs(result - 50) < 0.1
