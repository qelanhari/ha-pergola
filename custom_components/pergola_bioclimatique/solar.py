"""Pure solar geometry and target calculation functions."""

import math


def compute_profile_angle(
    elevation: float, azimuth: float, face_azimuth: float
) -> float:
    """Compute the profile angle of the sun relative to the pergola face.

    Returns the angle in degrees (0-180).
    """
    delta_azim = abs(azimuth - face_azimuth)
    if delta_azim >= 180:
        return 0.0

    elev_rad = math.radians(elevation)
    delta_rad = math.radians(delta_azim)
    cos_delta = math.cos(delta_rad)

    if abs(cos_delta) < 0.001:
        return 90.0

    tan_p = math.tan(elev_rad) / cos_delta
    angle = math.degrees(math.atan(tan_p))
    return angle + 180.0 if angle < 0 else angle


def compute_winter_target(
    profile_angle: float, calibration_offset: float, current_pos: float,
    max_opening_angle: float, step_size: float,
) -> float:
    """Compute winter mode target: follow sun up, hold maximum on descent."""
    raw_angle = profile_angle + calibration_offset
    percent = angle_to_percent(raw_angle, max_opening_angle)
    stepped = quantize(percent, step_size)
    return max(stepped, current_pos)


def compute_summer_target(
    profile_angle: float,
    calibration_offset: float,
    max_opening_angle: float,
    step_size: float,
    pitch_ratio: float,
    flip_profile_threshold: float,
    summer_blade_offset: float = 0.0,
    phase_a_intercept: float = 40.0,
) -> float:
    """Compute summer mode target.

    Output: HA cover tilt position percent. 0% = blades flat (rain
    position, cover "closed"). 100% = blades at max_opening_angle.

    Two phases with DIFFERENT models — calibrated independently against
    field observations:

    - phase A (profile_angle < flip_profile_threshold): **linear** ramp
      from (0, phase_a_intercept) to (flip_profile_threshold, 100).
      Empirical fit; the geometric cutoff formula has the wrong slope
      for real-blade physics in this regime.

    - phase B (profile_angle >= flip_profile_threshold): **cutoff**
      geometry,
          blade = profile − 90° + arccos(P/W·sin profile) + offset
      where offset = calibration_offset + summer_blade_offset.

    Calibration:
      - flip_profile_threshold = profile where rays first leak past
        fully-tilted blades.
      - phase_a_intercept = target at profile=0; tune so phase A's
        ramp passes through your observed "minimum closure to block"
        at any known profile (linear interpolation).
      - pitch_ratio + summer_blade_offset = phase B shape.
    """
    if profile_angle < flip_profile_threshold:
        # Phase A: linear ramp.
        if profile_angle <= 0:
            return quantize(phase_a_intercept, step_size)
        target_pct = (
            phase_a_intercept
            + (100.0 - phase_a_intercept)
            * profile_angle
            / flip_profile_threshold
        )
        return quantize(target_pct, step_size)

    # Phase B: cutoff geometry.
    sin_arg = pitch_ratio * math.sin(math.radians(profile_angle))
    if sin_arg >= 1.0:
        return 100.0  # degenerate (sun in face plane)
    delta = math.degrees(math.acos(sin_arg))
    blade = (
        profile_angle - 90.0
        + delta
        + calibration_offset + summer_blade_offset
    )
    if blade <= 0:
        return 100.0  # degenerate
    return quantize(
        angle_to_percent(blade, max_opening_angle), step_size
    )


def blade_cutoff_angle(profile_angle: float, pitch_ratio: float) -> float:
    """Blade tilt (deg) that just cuts off the direct beam between adjacent
    flat louvers, as a function of the sun's profile angle.

    This is the geometric core of the summer "phase B" law, extracted so the
    v2 model can reuse it. Returns the raw angle WITHOUT calibration
    offset or clamping — callers add the offset and clamp/convert.
    """
    sin_arg = pitch_ratio * math.sin(math.radians(profile_angle))
    if sin_arg >= 1.0:
        return profile_angle - 90.0  # degenerate (sun in face plane)
    return profile_angle - 90.0 + math.degrees(math.acos(sin_arg))


def compute_summer_target_v2(
    profile_angle: float,
    calibration_offset: float,
    max_opening_angle: float,
    step_size: float,
    pitch_ratio: float,
    flip_profile_threshold: float,
    summer_blade_offset: float = 0.0,
    phase_a_intercept: float = 40.0,
    bridge_deg: float = 6.0,
) -> float:
    """Summer target, **v2** — same physics as :func:`compute_summer_target`
    but with the phase-A→phase-B cliff removed.

    The original model jumps from 100 % at the flip straight to the (much
    lower) phase-B cutoff value in a single tick (e.g. 100 %→~10 %), slamming
    the blades flat then reopening. v2 splices a short linear bridge over
    ``[flip, flip + bridge_deg]`` so the command is C0-continuous.

    Phase A (``profile < flip``) is the unchanged empirical linear ramp.
    Phase B (``profile >= flip + bridge_deg``) is the unchanged cutoff law.
    """
    if profile_angle < flip_profile_threshold:
        if profile_angle <= 0:
            return quantize(phase_a_intercept, step_size)
        target_pct = (
            phase_a_intercept
            + (100.0 - phase_a_intercept)
            * profile_angle
            / flip_profile_threshold
        )
        return quantize(target_pct, step_size)

    def _cutoff_pct(profile: float) -> float:
        blade = (
            blade_cutoff_angle(profile, pitch_ratio)
            + calibration_offset
            + summer_blade_offset
        )
        if blade <= 0:
            return 100.0
        return angle_to_percent(blade, max_opening_angle)

    bridge_end = flip_profile_threshold + bridge_deg
    if bridge_deg > 0 and profile_angle < bridge_end:
        # Linear bridge from (flip, 100 %) to (bridge_end, cutoff%).
        end_pct = _cutoff_pct(bridge_end)
        frac = (profile_angle - flip_profile_threshold) / bridge_deg
        return quantize(100.0 + (end_pct - 100.0) * frac, step_size)

    return quantize(_cutoff_pct(profile_angle), step_size)


def compute_pv_threshold(
    sun_elevation: float, sun_azimuth: float,
    panel_azimuth: float, panel_tilt: float,
    pv_max: float, ratio: float,
) -> float:
    """Compute dynamic PV threshold for sun/cloud detection.

    Uses the angle-of-incidence cosine for a panel with the given azimuth
    and tilt, so the model reflects the actual roof orientation.
    """
    elev_rad = math.radians(sun_elevation)
    tilt_rad = math.radians(panel_tilt)
    delta_rad = math.radians(abs(sun_azimuth - panel_azimuth))

    cos_aoi = max(
        0.0,
        math.sin(elev_rad) * math.cos(tilt_rad)
        + math.cos(elev_rad) * math.sin(tilt_rad) * math.cos(delta_rad),
    )
    return cos_aoi * pv_max * ratio


def panel_cos_aoi(
    sun_elevation: float, sun_azimuth: float,
    panel_azimuth: float, panel_tilt: float,
) -> float:
    """Cosine of the angle of incidence on the panel. 0 if behind the panel."""
    elev_rad = math.radians(sun_elevation)
    tilt_rad = math.radians(panel_tilt)
    delta_rad = math.radians(abs(sun_azimuth - panel_azimuth))
    return max(
        0.0,
        math.sin(elev_rad) * math.cos(tilt_rad)
        + math.cos(elev_rad) * math.sin(tilt_rad) * math.cos(delta_rad),
    )


def is_sunny(
    pv_smooth: float, pv_threshold: float, pv_observable: bool,
    lux_smooth: float, lux_threshold: float, lux_observable: bool,
    previous_is_sunny: bool,
) -> bool:
    """Combine PV and lux signals with sun-position observability gates.

    OR-combine over observable sensors. When neither sensor can currently
    see direct sun, hold the previous decision so a momentary geometry
    blind-spot doesn't flip the state.
    """
    if not pv_observable and not lux_observable:
        return previous_is_sunny
    pv_says = pv_observable and pv_smooth > pv_threshold
    lux_says = lux_observable and lux_smooth > lux_threshold
    return pv_says or lux_says


def smooth_pv(raw: float, previous: float, alpha: float) -> float:
    """Exponential smoothing of PV power reading."""
    return round(alpha * raw + (1 - alpha) * previous, 1)


def quantize(value: float, step: float) -> float:
    """Round value to nearest multiple of step, clamped to 0-100."""
    stepped = round(value / step) * step
    return float(max(0, min(100, int(stepped))))


def angle_to_percent(angle: float, max_opening_angle: float) -> float:
    """Convert angle in degrees to percentage of max opening."""
    return (angle / max_opening_angle) * 100
