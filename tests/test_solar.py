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
    is_sunny,
    panel_cos_aoi,
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

    def test_no_hold_after_mode_switch(self) -> None:
        """After mode switch (current_pos=0), target follows solar freely."""
        result = compute_winter_target(
            profile_angle=30, calibration_offset=-10, current_pos=0,
            max_opening_angle=135, step_size=5,
        )
        # raw_angle=20, percent=20/135*100≈14.8%, quantize→15%
        assert result == 15.0

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
        """Legacy flip mode: side A > max and side B > 0 → flip to side B."""
        result = compute_summer_target(
            profile_angle=120, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
            side_fallback="flip",
        )
        # side_a = 210 > 135, side_b = 120-90-10 = 20 > 0
        # percent = 20/135*100 = 14.8% → quantize to 15%
        assert result == 15.0

    def test_flip_higher_profile(self) -> None:
        """Legacy flip: late afternoon, high profile → side B gives open position."""
        result = compute_summer_target(
            profile_angle=150, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
            side_fallback="flip",
        )
        # side_b = 150-90-10 = 50 → 50/135*100 = 37% → 35%
        assert result == 35.0

    def test_default_clamps_to_100_when_side_a_overflows(self) -> None:
        """Default behavior: when side A > max, stay at 100% (no flip)."""
        result = compute_summer_target(
            profile_angle=120, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
        )
        # Default side_fallback="clamp" — stays at 100% instead of flipping.
        assert result == 100.0

    def test_clamp_does_not_flip_at_overhead_sun(self) -> None:
        """Field case: profile 67.23° matches the operator-observed problem.

        With the legacy flip the cutoff side B yields ~5% (blades nearly
        flat), which the operator perceives as wide open. Clamping at 100%
        keeps the blades shut and matches the operator's intuition of
        "stay closed when the sun is overhead".
        """
        result = compute_summer_target(
            profile_angle=67.23, calibration_offset=-10,
            safety_margin=10, max_opening_angle=135, step_size=5,
            mode="cutoff", pitch_ratio=0.92,
        )
        # cutoff side_a ≈ 125.26 + (-10 + 10) = 125.26 ≤ 135 → side A used
        # → 92.78% → quantize 5 → 95%. Verified.
        assert result == 95.0

    def test_perpendicular_clamps_while_cutoff_ceiling_fits(self) -> None:
        """Field case: at profile=67.23°, perpendicular side_a (157°) overflows
        but the cutoff ceiling (125°) still fits in max=135°. At full closure
        the gaps are geometrically closed → stay at 100% regardless of mode.
        """
        result = compute_summer_target(
            profile_angle=67.23, calibration_offset=-10, safety_margin=10,
            max_opening_angle=135, step_size=5,
            mode="perpendicular", pitch_ratio=0.92,
        )
        assert result == 100.0

    def test_flip_only_triggers_past_ceiling(self) -> None:
        """Even with side_fallback='flip', the flip is suppressed while the
        cutoff ceiling fits in max — otherwise the algorithm would open up
        the pergola while it can still block 100% of direct rays.
        """
        # profile=67° → ceiling 125° ≤ 135° → no flip even if requested.
        result = compute_summer_target(
            profile_angle=67.23, calibration_offset=-10, safety_margin=10,
            max_opening_angle=135, step_size=5,
            mode="perpendicular", pitch_ratio=0.92, side_fallback="flip",
        )
        assert result == 100.0

    def test_clamp_with_smaller_max_angle(self) -> None:
        """When max is small enough that cutoff side A overflows, clamp wins."""
        result = compute_summer_target(
            profile_angle=67.23, calibration_offset=0,
            safety_margin=10, max_opening_angle=100, step_size=5,
            mode="cutoff", pitch_ratio=0.92,
        )
        # cutoff side_a = 125.26 + 10 = 135.26 > 100 → clamp → 100%
        assert result == 100.0

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


class TestComputeSummerTargetCutoff:
    def test_cutoff_less_closed_than_perpendicular(self) -> None:
        """At mid elevation, cutoff mode gives a smaller position than perpendicular."""
        perp = compute_summer_target(
            profile_angle=30, calibration_offset=0, safety_margin=0,
            max_opening_angle=135, step_size=5,
            mode="perpendicular",
        )
        cutoff = compute_summer_target(
            profile_angle=30, calibration_offset=0, safety_margin=0,
            max_opening_angle=135, step_size=5,
            mode="cutoff", pitch_ratio=0.92,
        )
        assert cutoff < perp

    def test_cutoff_zero_profile(self) -> None:
        """At profile 0, acos(0)=90° → raw_angle = 0 → 0%."""
        result = compute_summer_target(
            profile_angle=0, calibration_offset=0, safety_margin=0,
            max_opening_angle=135, step_size=5,
            mode="cutoff", pitch_ratio=0.92,
        )
        assert result == 0.0

    def test_cutoff_falls_through_to_side_b(self) -> None:
        """Legacy flip: high profile → side_a exceeds max → cutoff side_b used."""
        result = compute_summer_target(
            profile_angle=120, calibration_offset=-10, safety_margin=10,
            max_opening_angle=135, step_size=5,
            mode="cutoff", pitch_ratio=0.92, side_fallback="flip",
        )
        # cutoff side_a ≈ 172.9° (exceeds 135)
        # cutoff side_b = 120 - 90 + arccos(0.92·sin120°) = 67.1°
        # + cal(-10) = 57.1° → 42.3% → quantized step 5 → 40%
        assert result == 40.0

    def test_cutoff_side_b_matches_field_30_percent(self) -> None:
        """Legacy flip field-tested: profile 105.6° → 30% via side B."""
        result = compute_summer_target(
            profile_angle=105.6, calibration_offset=0, safety_margin=10,
            max_opening_angle=135, step_size=5,
            mode="cutoff", pitch_ratio=0.92, side_fallback="flip",
        )
        assert result == 30.0

    def test_perpendicular_side_b_unchanged(self) -> None:
        """Legacy flip perpendicular: simple side_b fallback."""
        result = compute_summer_target(
            profile_angle=105.6, calibration_offset=0, safety_margin=10,
            max_opening_angle=135, step_size=5,
            mode="perpendicular", side_fallback="flip",
        )
        # side_a = 105.6 + 90 + 10 = 205.6 > 135 → side_b = 105.6 - 90 = 15.6
        # /135*100 = 11.55 → quantized step 5 → 10%
        assert result == 10.0

    def test_cutoff_pitch_ratio_one_matches_side_a_bound(self) -> None:
        """With P/W=1 at profile=90°, sin_arg=1 → infeasible → side B path."""
        result = compute_summer_target(
            profile_angle=90, calibration_offset=-10, safety_margin=0,
            max_opening_angle=135, step_size=5,
            mode="cutoff", pitch_ratio=1.0,
        )
        # side_a infeasible → side_b = 90-90-10 = -10 ≤ 0 → 100%
        assert result == 100.0


class TestComputePvThreshold:
    def test_low_elevation_no_floor(self) -> None:
        """Threshold scales with cos(AoI) — no 400 W floor anymore."""
        result = compute_pv_threshold(
            sun_elevation=5, sun_azimuth=130,
            panel_azimuth=180, panel_tilt=30,
            pv_max=3000, ratio=0.70,
        )
        # cos_aoi at elev=5°, |Δaz|=50° on 30° panel ≈ 0.4 → ~840W
        assert 700 < result < 900

    def test_face_on_sun_gives_near_peak_threshold(self) -> None:
        """Sun at 50°/180° on a south-facing 30° panel → cos_aoi ≈ 0.985."""
        result = compute_pv_threshold(
            sun_elevation=50, sun_azimuth=180,
            panel_azimuth=180, panel_tilt=30,
            pv_max=3000, ratio=0.70,
        )
        # 0.985 × 3000 × 0.70 ≈ 2069
        assert 2000 < result < 2150

    def test_off_axis_lower_threshold(self) -> None:
        """Sun at 35°/250° on a south-facing 30° panel → cos_aoi ≈ 0.637."""
        result = compute_pv_threshold(
            sun_elevation=35, sun_azimuth=250,
            panel_azimuth=180, panel_tilt=30,
            pv_max=3000, ratio=0.70,
        )
        # 0.637 × 3000 × 0.70 ≈ 1338
        assert 1280 < result < 1400

    def test_sun_behind_panel_zero(self) -> None:
        """Sun far behind panel → cos_aoi clamped to 0 → threshold 0."""
        result = compute_pv_threshold(
            sun_elevation=10, sun_azimuth=0,
            panel_azimuth=180, panel_tilt=30,
            pv_max=3000, ratio=0.70,
        )
        assert result == 0.0


class TestPanelCosAoi:
    def test_normal_incidence(self) -> None:
        # Sun at panel azimuth, elev = 90° - tilt → ray normal to panel
        result = panel_cos_aoi(60, 180, 180, 30)
        assert abs(result - 1.0) < 0.01

    def test_behind_panel_clamped(self) -> None:
        result = panel_cos_aoi(10, 0, 180, 30)
        assert result == 0.0


class TestIsSunny:
    def test_pv_only_sees_sun_and_passes(self) -> None:
        # Lux not observable; PV observable and above threshold
        assert is_sunny(1000, 500, True, 0, 0, False, False) is True

    def test_pv_only_sees_sun_and_fails(self) -> None:
        assert is_sunny(100, 500, True, 0, 0, False, True) is False

    def test_lux_only_sees_sun_and_passes(self) -> None:
        assert is_sunny(0, 0, False, 30000, 20000, True, False) is True

    def test_either_signal_passes_is_sunny(self) -> None:
        # OR semantics: PV says no, lux says yes → sunny
        assert is_sunny(100, 500, True, 30000, 20000, True, False) is True

    def test_neither_observable_holds_previous_true(self) -> None:
        # Both shaded → keep previous decision (sunny)
        assert is_sunny(0, 0, False, 0, 0, False, True) is True

    def test_neither_observable_holds_previous_false(self) -> None:
        # Both shaded → keep previous decision (cloudy) — sunrise default
        assert is_sunny(0, 0, False, 0, 0, False, False) is False

    def test_both_observable_both_below(self) -> None:
        assert is_sunny(100, 500, True, 1000, 20000, True, True) is False


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
