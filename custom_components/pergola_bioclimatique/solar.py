"""Pure solar geometry and target calculation functions."""

import math
from datetime import datetime


def azimuth_delta(azimuth: float, reference: float) -> float:
    """Smallest absolute angular difference between two azimuths (0-180°).

    Handles the 0/360 wraparound: delta(350°, 10°) is 20°, not 340°.
    """
    delta = abs(azimuth - reference) % 360.0
    return 360.0 - delta if delta > 180.0 else delta


def azimuth_in_window(
    azimuth: float, az_min: float, az_max: float
) -> bool:
    """True if azimuth lies in the clockwise arc from az_min to az_max.

    Handles windows that cross north (e.g. a north-facing pergola with
    face ± 90° = [280°, 100°]) and raw config values outside 0-360
    (face_azimuth − 90 can be negative). A span of 360° or more means
    the whole circle.
    """
    if az_max - az_min >= 360.0:
        return True
    azimuth %= 360.0
    az_min %= 360.0
    az_max %= 360.0
    if az_min <= az_max:
        return az_min <= azimuth <= az_max
    return azimuth >= az_min or azimuth <= az_max


def compute_profile_angle(
    elevation: float, azimuth: float, face_azimuth: float
) -> float:
    """Compute the profile angle of the sun relative to the pergola face.

    Returns the angle in degrees (0-180).
    """
    delta_azim = azimuth_delta(azimuth, face_azimuth)
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
    cloudy_target: float | None = None,
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
      Capped when ``cloudy_target`` is provided: perpendicular blades
      (90° of max_opening_angle) are the last position that still
      projects shade — past it the geometry keeps opening toward 100%,
      but that's tracking sun the blades can no longer block. The cap
      is ``min(cloudy_target, perpendicular)``: cloudy_target can only
      lower the resting point, never push tracking past perpendicular.
      Phase B ramps up to the cap and rests there.

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
        pct = 100.0  # degenerate (sun in face plane)
    else:
        delta = math.degrees(math.acos(sin_arg))
        blade = (
            profile_angle - 90.0
            + delta
            + calibration_offset + summer_blade_offset
        )
        if blade <= 0:
            pct = 100.0  # degenerate
        else:
            pct = quantize(
                angle_to_percent(blade, max_opening_angle), step_size
            )
    # Cap at the last shade-casting position: perpendicular blades, or
    # the cloudy resting position if the user set it lower. Quantized so
    # the capped target matches the coordinator's quantized final.
    if cloudy_target is not None:
        perpendicular = angle_to_percent(90.0, max_opening_angle)
        cap = quantize(min(float(cloudy_target), perpendicular), step_size)
        pct = min(pct, cap)
    return pct


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
    delta_rad = math.radians(azimuth_delta(sun_azimuth, panel_azimuth))

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
    delta_rad = math.radians(azimuth_delta(sun_azimuth, panel_azimuth))
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


def is_recent_save(
    saved_at_iso: str | None, now: datetime, max_age_seconds: float,
) -> bool:
    """True if a persisted-state timestamp is same-day and recent.

    Used to decide whether a restored ``is_sunny`` can be trusted after a
    restart/reload: a save from a few minutes ago (entry reload, HA
    restart) is still valid; yesterday evening's save is not — the first
    morning decision must not inherit it.
    """
    if not saved_at_iso:
        return False
    try:
        saved_at = datetime.fromisoformat(saved_at_iso)
    except (ValueError, TypeError):
        return False
    if saved_at.date() != now.date():
        return False
    age = (now - saved_at).total_seconds()
    return 0 <= age <= max_age_seconds


def smooth_pv(raw: float, previous: float, alpha: float) -> float:
    """Exponential smoothing of PV power reading."""
    return round(alpha * raw + (1 - alpha) * previous, 1)


def quantize(value: float, step: float) -> float:
    """Round value to nearest multiple of step, clamped to 0-100."""
    stepped = round(value / step) * step
    return float(max(0.0, min(100.0, stepped)))


def angle_to_percent(angle: float, max_opening_angle: float) -> float:
    """Convert angle in degrees to percentage of max opening."""
    return (angle / max_opening_angle) * 100
