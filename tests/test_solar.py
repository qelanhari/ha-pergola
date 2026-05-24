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
    """Threshold-based summer algorithm.

    profile < flip_profile_threshold → 100% (side A clamp).
    profile >= flip_profile_threshold → side B cutoff geometry.
    """

    def test_phase_a_tracks_sun_progressively(self) -> None:
        """Phase A is no longer a flat clamp at 100 % — it follows the
        cutoff side A geometry. profile=40 → blade ≈ 76°, ~55 %."""
        result = compute_summer_target(
            profile_angle=40, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        # 40 + 90 − arccos(0.92·sin40°) = 130 − arccos(0.591) = 76.26°
        # 76.26/135 = 56.5 % → quantize step 5 → 55
        assert result == 55.0

    def test_phase_a_field_case_at_67_degrees(self) -> None:
        """Field observation 13h on 23 May 2026: profile=67° → ~93 % → 95%
        (matches the operator's "90 % was right" intuition closely)."""
        result = compute_summer_target(
            profile_angle=67.23, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        # 67.23 + 90 − arccos(0.92·sin67.23°) = 157.23 − 31.96 = 125.27°
        # 125.27/135 = 92.79 % → quantize → 95
        assert result == 95.0

    def test_phase_a_clamps_at_100_when_blade_overflows(self) -> None:
        """profile=82° with threshold=85° stays in phase A; blade overflows
        max_opening_angle → clamp 100 %."""
        result = compute_summer_target(
            profile_angle=82, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
        )
        # 82 + 90 − arccos(0.92·sin82°) = 172 − 24.27 = 147.73 > 135 → 100
        assert result == 100.0

    def test_phase_a_zero_profile_returns_rain_position(self) -> None:
        """profile=0: blade = 0+90−arccos(0) = 0° → 0 % (rain position)."""
        result = compute_summer_target(
            profile_angle=0, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        assert result == 0.0

    def test_afternoon_just_after_flip(self) -> None:
        """Field observation 14h45 on 23 May 2026: profile≈82°, offset=0,
        P/W=0.92 → side B cutoff = -8 + arccos(0.911) = 16.27° → 12% →
        quantize step 5 → 10."""
        result = compute_summer_target(
            profile_angle=82, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        assert result == 10.0

    def test_afternoon_field_case_with_offset_yields_15(self) -> None:
        """Same sun position with offset=+4 shifts side B into the 15% band."""
        result = compute_summer_target(
            profile_angle=82, calibration_offset=4,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        # 16.27 + 4 = 20.27° → 15.02% → quantize step 5 → 15
        assert result == 15.0

    def test_threshold_boundary_is_inclusive(self) -> None:
        """profile = threshold → flip branch applies (>=, not >)."""
        result = compute_summer_target(
            profile_angle=80, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        # 80 − 90 + arccos(0.92·sin80°) = −10 + 25.06 = 15.06°
        # → 11.16% → quantize step 5 → 10
        assert result == 10.0

    def test_side_b_negative_clamps_to_100(self) -> None:
        """Degenerate case: negative side B angle after offset → 100%."""
        result = compute_summer_target(
            profile_angle=82, calibration_offset=-30,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        # side_b = 16.27 − 30 = −13.73 ≤ 0 → 100
        assert result == 100.0

    def test_high_profile_late_afternoon(self) -> None:
        """Sun further west (profile=120°) → side B angle much higher."""
        result = compute_summer_target(
            profile_angle=120, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        # 120 − 90 + arccos(0.92·sin120°) = 30 + 37.16 = 67.16°
        # → 49.7% → quantize → 50
        assert result == 50.0

    def test_summer_blade_offset_shifts_phase_a_earlier(self) -> None:
        """Field case 2026-05-24: at profile=50°, default algo gave 70 %.
        With summer_blade_offset=+5, blade ≈ 99.84° → 73.96 % → quantize 75.
        This is the empirical knob the user tunes when the bascule arrives
        a few minutes late.
        """
        result = compute_summer_target(
            profile_angle=50, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            summer_blade_offset=5,
        )
        assert result == 75.0

    def test_summer_blade_offset_also_affects_phase_b(self) -> None:
        """Same +5° offset glides phase B up by ~3.7 % — acceptable side
        effect. profile=87° (post-bascule yesterday): blade = 21.27 + 5 →
        26.27° → 19.5 % → quantize 20 (was 15)."""
        result = compute_summer_target(
            profile_angle=87, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            summer_blade_offset=5,
        )
        assert result == 20.0

    def test_lower_pitch_ratio_yields_higher_post_flip(self) -> None:
        """A user with thicker blades (lower P/W) calibrates pitch_ratio down;
        the post-flip target is then higher (blades closer to vertical)."""
        result = compute_summer_target(
            profile_angle=82, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.79, flip_profile_threshold=80,
        )
        # 82 − 90 + arccos(0.79·sin82°) = −8 + arccos(0.782) = −8 + 38.55
        # = 30.55° → 22.6% → quantize → 25
        # (also note: with P/W=0.79 + offset=−10, the field 15% target lands
        #  almost exactly — see plan doc for the calibration arithmetic.)
        assert result == 25.0


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
