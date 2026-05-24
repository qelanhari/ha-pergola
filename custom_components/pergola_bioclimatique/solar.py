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
) -> float:
    """Compute summer mode target.

    Output: HA cover tilt position percent. 0% = blades flat (rain
    position, cover "closed"). 100% = blades at max_opening_angle
    (cover "open" in HA terms, but the slat overlap on side A still
    blocks all direct rays up to the empirical bascule threshold).

    Two phases, both using cutoff geometry:

    - phase A (profile_angle < flip_profile_threshold): blades on side A,
          blade = profile + 90° − arccos(P/W·sin profile) + offset
      Tracks the sun as it climbs; clamps at 100 % when the geometry
      reaches the mechanical limit; returns 0 % at the bottom (rain
      position).

    - phase B (profile_angle >= flip_profile_threshold): blades on side B,
          blade = profile − 90° + arccos(P/W·sin profile) + offset

    Calibration: the user picks `flip_profile_threshold` by watching
    `sensor.pergola_profile_angle` the moment the first ray leaks past
    the fully-tilted blades, and tunes `pitch_ratio` so the post-flip
    value matches the visually-optimal blade position.
    """
    sin_arg = pitch_ratio * math.sin(math.radians(profile_angle))
    if sin_arg >= 1.0:
        return 100.0  # degenerate (sun in face plane)

    delta = math.degrees(math.acos(sin_arg))

    if profile_angle < flip_profile_threshold:
        # Phase A: side A cutoff — blades track the sun progressively.
        blade = profile_angle + 90.0 - delta + calibration_offset
        if blade <= 0:
            return 0.0  # below mechanical range (rain position)
        if blade >= max_opening_angle:
            return 100.0  # above mechanical range
        return quantize(
            angle_to_percent(blade, max_opening_angle), step_size
        )

    # Phase B: side B cutoff.
    blade = profile_angle - 90.0 + delta + calibration_offset
    if blade <= 0:
        return 100.0  # degenerate
    return quantize(
        angle_to_percent(blade, max_opening_angle), step_size
    )


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
