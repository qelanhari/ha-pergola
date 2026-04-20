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
    profile_angle: float, calibration_offset: float,
    safety_margin: float, max_opening_angle: float, step_size: float,
    mode: str = "perpendicular", pitch_ratio: float = 0.92,
) -> float:
    """Compute summer mode target.

    mode="perpendicular": blades perpendicular to sun rays (full blocking).
      side_a = profile_angle + 90°.

    mode="cutoff": blades rotated only enough to block direct rays through
      the gap between adjacent blades, given the pitch/width ratio.
      side_a = profile_angle + 90° - arccos((P/W) * sin(profile_angle)).
      Less closed than perpendicular → more airflow and diffuse light.

    If side A exceeds max_opening_angle, falls back to side B (other blade
    face): side B = profile_angle - 90° + offset. If side B ≤ 0, stays at
    100% (best available shade).
    """
    side_a = _summer_side_a(profile_angle, mode, pitch_ratio) \
        + calibration_offset + safety_margin

    if side_a <= max_opening_angle:
        percent = angle_to_percent(side_a, max_opening_angle)
        return quantize(percent, step_size)

    # Side A exceeds max → fall back to side B using the same mode
    side_b = _summer_side_b(profile_angle, mode, pitch_ratio) + calibration_offset
    if side_b <= 0:
        return 100.0

    percent = angle_to_percent(side_b, max_opening_angle)
    return quantize(percent, step_size)


def _summer_side_a(
    profile_angle: float, mode: str, pitch_ratio: float,
) -> float:
    """Blade raw angle for side A before offsets/margin."""
    if mode != "cutoff":
        return profile_angle + 90

    sin_arg = pitch_ratio * math.sin(math.radians(profile_angle))
    if sin_arg >= 1.0:
        # No cutoff solution on side A → force fallback to side B
        return float("inf")
    delta = math.degrees(math.acos(sin_arg))
    return profile_angle + 90 - delta


def _summer_side_b(
    profile_angle: float, mode: str, pitch_ratio: float,
) -> float:
    """Blade raw angle for side B (fallback) before offset."""
    if mode != "cutoff":
        return profile_angle - 90

    sin_arg = pitch_ratio * math.sin(math.radians(profile_angle))
    if sin_arg >= 1.0:
        return profile_angle - 90
    delta = math.degrees(math.acos(sin_arg))
    return profile_angle - 90 + delta


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
    return max(400.0, cos_aoi * pv_max * ratio)


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
