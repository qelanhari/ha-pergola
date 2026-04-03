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
) -> float:
    """Compute summer mode target: maximum shadow, flip if exceeds max."""
    s_raw = profile_angle + 90 + calibration_offset + safety_margin
    if s_raw <= max_opening_angle:
        raw_angle = s_raw
    else:
        raw_angle = profile_angle - 90 + calibration_offset

    percent = angle_to_percent(raw_angle, max_opening_angle)
    return quantize(percent, step_size)


def compute_pv_threshold(
    azimuth: float, elevation: float, face_azimuth: float,
    pv_max: float, ratio: float,
) -> float:
    """Compute dynamic PV threshold for sun/cloud detection.

    Uses angle-of-incidence cosine with a 30° panel tilt.
    """
    elev_rad = math.radians(elevation)
    delta_rad = math.radians(abs(azimuth - face_azimuth))
    panel_tilt_rad = math.radians(30)

    cos_aoi = max(
        0.0,
        math.sin(elev_rad) * math.cos(panel_tilt_rad)
        + math.cos(elev_rad) * math.sin(panel_tilt_rad) * math.cos(delta_rad),
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
