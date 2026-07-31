"""Tests for solar geometry functions."""

import math
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Import solar module directly to avoid homeassistant dependency
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "pergola_bioclimatique")
)
from solar import (  # noqa: E402
    angle_to_percent,
    azimuth_delta,
    azimuth_in_window,
    compute_profile_angle,
    compute_pv_threshold,
    compute_summer_target,
    compute_winter_target,
    is_recent_save,
    is_sunny,
    panel_cos_aoi,
    quantize,
    rain_hold_active,
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

    def test_north_facing_wraparound(self) -> None:
        """face=10°, sun az=350° is a 20° delta across north — must equal
        the mirrored az=30° case, not read as a 340° delta (→ 0)."""
        across_north = compute_profile_angle(45, 350, 10)
        mirrored = compute_profile_angle(45, 30, 10)
        assert abs(across_north - mirrored) < 0.001
        assert across_north > 40  # real profile, not the 0 fallback


class TestAzimuthHelpers:
    @pytest.mark.parametrize(
        ("azimuth", "reference", "expected"),
        [
            (350, 10, 20),     # across north
            (10, 350, 20),     # symmetric
            (130, 130, 0),
            (220, 130, 90),
            (310, 130, 180),   # directly opposite
            (-10, 10, 20),     # negative input normalizes
        ],
    )
    def test_azimuth_delta(self, azimuth, reference, expected) -> None:
        assert azimuth_delta(azimuth, reference) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("azimuth", "az_min", "az_max", "expected"),
        [
            (130, 40, 220, True),     # plain window (face=130 defaults)
            (300, 40, 220, False),
            (40, 40, 220, True),      # bounds inclusive
            (220, 40, 220, True),
            (350, 280, 100, True),    # window crossing north
            (10, 280, 100, True),
            (180, 280, 100, False),
            (350, -80, 100, True),    # raw face−90 default for face=10
            (200, -80, 100, False),
            (123, 0, 360, True),      # full circle = always in
        ],
    )
    def test_azimuth_in_window(
        self, azimuth, az_min, az_max, expected
    ) -> None:
        assert azimuth_in_window(azimuth, az_min, az_max) is expected


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
    """Linear phase A + cutoff phase B summer algorithm.

    Phase A (profile < flip_profile_threshold): linear interpolation
    from (0, phase_a_intercept) to (flip_threshold, 100%).

    Phase B (profile >= flip_threshold): cutoff side B formula
    (calibration_offset + summer_blade_offset apply here).
    """

    def test_phase_a_linear_ramp_at_intercept_default(self) -> None:
        """profile=40, threshold=80, intercept=40 (default):
        target = 40 + 60·40/80 = 70."""
        result = compute_summer_target(
            profile_angle=40, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            phase_a_intercept=40,
        )
        assert result == 70.0

    def test_phase_a_field_three_points_colinear(self) -> None:
        """Three field observations (face_az=130°, threshold=85°,
        intercept=40) lie on the linear ramp:
          - profile=50 → 75% (morning, just enough to block)
          - profile=64 → 85% (mid-day, observed minimum)
          - profile=84.9 → 100% (asymptote at the threshold)

        profile=85 itself crosses into phase B (cutoff side B → 15%);
        that's tested separately.
        """
        for profile, expected in [(50, 75), (64, 85), (84.9, 100)]:
            result = compute_summer_target(
                profile_angle=profile, calibration_offset=0,
                max_opening_angle=135, step_size=5,
                pitch_ratio=0.92, flip_profile_threshold=85,
                phase_a_intercept=40,
            )
            assert result == float(expected), (
                f"profile={profile}: expected {expected}, got {result}"
            )

    def test_phase_a_intercept_zero(self) -> None:
        """With intercept=0, phase A is a pure 0 → 100 linear ramp."""
        result = compute_summer_target(
            profile_angle=42.5, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            phase_a_intercept=0,
        )
        # target = 0 + 100·42.5/85 = 50
        assert result == 50.0

    def test_phase_a_zero_profile_returns_intercept(self) -> None:
        """profile=0 → target = intercept (theoretical, in practice
        masked by sun_az_min in the coordinator)."""
        result = compute_summer_target(
            profile_angle=0, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            phase_a_intercept=40,
        )
        assert result == 40.0

    def test_phase_a_overflow_clamps_at_100(self) -> None:
        """Linear interpolation can exceed 100 if profile briefly tops
        the threshold without crossing into phase B; quantize clamps."""
        result = compute_summer_target(
            profile_angle=84, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            phase_a_intercept=40,
        )
        # 40 + 60·84/85 = 99.29 → quantize 100
        assert result == 100.0

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

    def test_summer_blade_offset_does_not_affect_phase_a(self) -> None:
        """v1.13.3+: summer_blade_offset is phase B only. Phase A is the
        linear ramp regardless of the offset."""
        result = compute_summer_target(
            profile_angle=50, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            summer_blade_offset=10,
            phase_a_intercept=40,
        )
        # Linear: 40 + 60·50/85 = 75.29 → quantize 75 (offset ignored)
        assert result == 75.0

    def test_summer_blade_offset_still_affects_phase_b(self) -> None:
        """Phase B remains tunable via summer_blade_offset."""
        result = compute_summer_target(
            profile_angle=87, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            summer_blade_offset=5,
            phase_a_intercept=40,
        )
        # Phase B blade = -3 + arccos(0.917) + 0 + 5 = 25.31° → 18.7% → 20
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

    def test_phase_b_capped_at_cloudy_target(self) -> None:
        """Past perpendicular the cutoff keeps opening (here 75%), but with
        cloudy_target set, phase B rests at the perpendicular/cloudy value."""
        result = compute_summer_target(
            profile_angle=140, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            cloudy_target=60,
        )
        # uncapped: 140−90+arccos(0.92·sin140°) = 50+53.78 = 103.78° → 75%
        # capped at cloudy_target → 60
        assert result == 60.0

    def test_phase_b_below_cloudy_target_uncapped(self) -> None:
        """Below the cap, phase B is unchanged — it ramps freely up to it."""
        result = compute_summer_target(
            profile_angle=120, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            cloudy_target=60,
        )
        # cutoff = 50% (see test_high_profile_late_afternoon); 50 < 60 → 50
        assert result == 50.0

    def test_phase_b_cap_none_is_uncapped(self) -> None:
        """No cloudy_target (default) preserves the raw cutoff curve."""
        result = compute_summer_target(
            profile_angle=140, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
        )
        assert result == 75.0

    def test_cap_does_not_affect_phase_a(self) -> None:
        """The cap is phase-B only; phase A still ramps toward 100%."""
        result = compute_summer_target(
            profile_angle=50, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=85,
            phase_a_intercept=40, cloudy_target=60,
        )
        # Linear: 40 + 60·50/85 = 75.29 → 75 (above cloudy_target, not capped)
        assert result == 75.0

    def test_degenerate_open_capped_when_cloudy_target_set(self) -> None:
        """Degenerate 100% (negative blade) is also capped at cloudy_target."""
        result = compute_summer_target(
            profile_angle=82, calibration_offset=-30,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            cloudy_target=60,
        )
        # side_b = −13.73 ≤ 0 → 100 uncapped → capped to 60
        assert result == 60.0

    def test_cap_bounded_by_perpendicular(self) -> None:
        """cloudy_target above perpendicular can't push tracking past it:
        blades stop casting shade past 90°, so the cap is min(cloudy,
        perpendicular) — a cloudy_target=80 user doesn't get the leak back."""
        result = compute_summer_target(
            profile_angle=140, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            cloudy_target=80,
        )
        # uncapped 75; perpendicular = 90/135 = 66.67 → cap quantize(66.67)=65
        assert result == 65.0

    def test_cap_is_quantized(self) -> None:
        """The cap is quantized so the capped solar_target equals the
        coordinator's quantized final (cloudy 66 → 65 at step 5)."""
        result = compute_summer_target(
            profile_angle=140, calibration_offset=0,
            max_opening_angle=135, step_size=5,
            pitch_ratio=0.92, flip_profile_threshold=80,
            cloudy_target=66,
        )
        assert result == 65.0

    def test_phase_b_monotonic_ramp_then_flat_at_cap(self) -> None:
        """Afternoon sweep: target never decreases, ends flat at the cap."""
        cap = 60.0  # quantize(min(60, 66.67), 5)
        prev = 0.0
        for profile in range(80, 151):
            result = compute_summer_target(
                profile_angle=float(profile), calibration_offset=0,
                max_opening_angle=135, step_size=5,
                pitch_ratio=0.92, flip_profile_threshold=80,
                cloudy_target=60,
            )
            assert result >= prev, f"profile={profile}: {result} < {prev}"
            assert result <= cap
            prev = result
        assert prev == cap  # the sweep reaches and rests at the cap


class TestIsRecentSave:
    NOW = datetime(2026, 6, 12, 15, 0, 0)

    @pytest.mark.parametrize(
        ("saved_at", "expected"),
        [
            ("2026-06-12T14:55:00", True),    # 5 min ago, same day
            ("2026-06-12T14:00:00", True),    # exactly max age
            ("2026-06-12T13:59:00", False),   # past max age
            ("2026-06-11T14:55:00", False),   # yesterday, same clock time
            ("2026-06-12T15:05:00", False),   # in the future (clock skew)
            ("not-a-date", False),            # garbage
            (None, False),                    # legacy store without saved_at
        ],
    )
    def test_freshness_window(self, saved_at, expected) -> None:
        assert is_recent_save(saved_at, self.NOW, 3600) is expected


class TestRainHoldActive:
    """The hold that stops the integration commanding a pergola in the rain.

    The control unit closes the blades on its own rain signal and refuses
    ours, so the only job here is deciding *how long* to stay quiet. The
    delay is measured from when rain was last *seen*, not from the entity's
    last_changed — see test_never_rained_never_holds for why.
    """

    @pytest.mark.parametrize("seconds", [0, 60, 600, 86400])
    def test_on_always_holds(self, seconds: float) -> None:
        """A wet sensor holds regardless of how long it's been wet."""
        assert rain_hold_active(True, seconds, 10) is True

    def test_on_holds_even_with_no_timestamp(self) -> None:
        """First-ever rain: no last-on stamp yet, but it's raining now."""
        assert rain_hold_active(True, None, 10) is True

    def test_never_rained_never_holds(self) -> None:
        """The v1.20.0 regression this replaced.

        A dry sensor with no recorded rain must not hold. Previously the
        delay ran off the entity's last_changed, which an HA restart
        resets — so every restart held the pergola for a full window in
        clear weather.
        """
        assert rain_hold_active(False, None, 10) is False

    @pytest.mark.parametrize(
        ("seconds_since_last_on", "expected"),
        [
            (0, True),      # just went dry
            (300, True),    # 5 min into a 10 min delay
            (599, True),    # one second short of release
            (600, False),   # exactly the delay — released
            (601, False),   # past the delay
            (86400, False),  # last rained yesterday
        ],
    )
    def test_clear_delay_window(
        self, seconds_since_last_on: float, expected: bool
    ) -> None:
        assert rain_hold_active(
            False, seconds_since_last_on, 10
        ) is expected

    @pytest.mark.parametrize("seconds", [0, 1, 600, 86400])
    def test_zero_delay_is_passthrough(self, seconds: float) -> None:
        """delay=0 trusts the entity — for a source that debounces itself."""
        assert rain_hold_active(False, seconds, 0) is False
        assert rain_hold_active(True, seconds, 0) is True

    def test_negative_delay_treated_as_zero(self) -> None:
        """Guard against a hand-edited entry storing a negative delay."""
        assert rain_hold_active(False, 0, -5) is False

    def test_fractional_delay(self) -> None:
        """Delay need not be whole minutes."""
        assert rain_hold_active(False, 20, 0.5) is True
        assert rain_hold_active(False, 40, 0.5) is False


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

    def test_north_facing_panel_wraparound(self) -> None:
        """Panel az=10°: sun at az=350° must read the same as az=30°
        (20° off-axis either side), not as behind the panel."""
        west_of_north = panel_cos_aoi(40, 350, 10, 30)
        east_of_north = panel_cos_aoi(40, 30, 10, 30)
        assert west_of_north == pytest.approx(east_of_north)
        assert west_of_north > 0.5


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

    def test_fractional_step(self) -> None:
        """Fractional steps must not be truncated to int (67.5 ≠ 67)."""
        assert quantize(67.5, 2.5) == 67.5
        assert quantize(66, 2.5) == 65.0


class TestAngleToPercent:
    def test_zero(self) -> None:
        assert angle_to_percent(0, 135) == 0

    def test_max(self) -> None:
        assert abs(angle_to_percent(135, 135) - 100) < 0.1

    def test_half(self) -> None:
        result = angle_to_percent(67.5, 135)
        assert abs(result - 50) < 0.1
