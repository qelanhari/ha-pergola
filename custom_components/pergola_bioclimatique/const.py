"""Constants for the Pergola Bioclimatique integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

DOMAIN = "pergola_bioclimatique"


def entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Read a config value, options taking precedence over install data.

    The single source of truth for that precedence. Anything reading
    ``entry.data`` directly would miss values the Options flow changed —
    which is every entity now that entities are editable at runtime.
    """
    return entry.options.get(key, entry.data.get(key, default))

# Config keys — Step 1: Entity selection
CONF_COVER_ENTITY = "cover_entity"
CONF_SUN_AZIMUTH_ENTITY = "sun_azimuth_entity"
CONF_SUN_ELEVATION_ENTITY = "sun_elevation_entity"
CONF_PV_POWER_ENTITY = "pv_power_entity"
CONF_LIGHT_SENSOR_ENTITY = "light_sensor_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_RAIN_ENTITY = "rain_entity"
CONF_PRIORITY_LOCK_ENTITY = "priority_lock_entity"
# Unread since v1.21.0: the controller's lock timer proved unreliable and
# hard to get updates on, so nothing derives timing from it any more. The
# key is kept so existing entries importing it don't break; it is no longer
# offered in the config flow.
CONF_PRIORITY_LOCK_TIMER_ENTITY = "priority_lock_timer_entity"

# Config keys — Step 2: Geometry
CONF_PERGOLA_MODEL = "pergola_model"
CONF_FACE_AZIMUTH = "face_azimuth"
CONF_MAX_OPENING_ANGLE = "max_opening_angle"
CONF_CALIBRATION_OFFSET = "calibration_offset"
CONF_BLADE_PITCH_RATIO = "blade_pitch_ratio"
CONF_FLIP_PROFILE_THRESHOLD = "flip_profile_threshold"
CONF_SUN_AZ_MIN = "sun_az_min"
CONF_SUN_AZ_MAX = "sun_az_max"
CONF_SUMMER_BLADE_OFFSET = "summer_blade_offset"
CONF_PHASE_A_INTERCEPT = "phase_a_intercept"

# Config keys — Step 3: Operation
CONF_UPDATE_INTERVAL = "update_interval"
CONF_STEP_SIZE = "step_size"
CONF_DEADBAND = "deadband"
CONF_CLOUDY_TARGET = "cloudy_target"
CONF_MIN_USEFUL_PERCENT = "min_useful_percent"
CONF_HUMIDITY_MAX = "humidity_max"
CONF_MIN_ELEVATION = "min_elevation"
CONF_RAIN_CLEAR_DELAY = "rain_clear_delay"

# Config keys — Step 4: Cloud detection
CONF_PV_MAX_WATTS = "pv_max_watts"
CONF_PV_SUNNY_RATIO = "pv_sunny_ratio"
CONF_PV_SMOOTH_ALPHA = "pv_smooth_alpha"
CONF_HYSTERESIS_DURATION = "hysteresis_duration"
CONF_PV_PANEL_AZIMUTH = "pv_panel_azimuth"
CONF_PV_PANEL_TILT = "pv_panel_tilt"
CONF_LUX_SUNNY_RATIO = "lux_sunny_ratio"
CONF_PV_OBSERVABLE_COS = "pv_observable_cos"
CONF_LUX_AZ_MIN = "lux_az_min"
CONF_LUX_AZ_MAX = "lux_az_max"

# Defaults — Geometry
# Pergola model preset identifier. "custom" means "use integration defaults"
# (legacy v1.14 behavior). Stored in config entry but never read by the
# coordinator — purely a UI hint so the Options flow can pre-select the
# user's chosen model. See presets.py for the full list of supported models.
DEFAULT_PERGOLA_MODEL = "custom"
DEFAULT_FACE_AZIMUTH = 130
DEFAULT_MAX_OPENING_ANGLE = 135
DEFAULT_CALIBRATION_OFFSET = -10
DEFAULT_BLADE_PITCH_RATIO = 0.92

# Empirical bascule threshold in degrees of profile_angle.
# Below this profile, blades stay clamped at 100% (side A overlap blocks
# all direct rays). At or above, blades flip to side B (cutoff geometry).
# Calibrated by observation: watch sensor.pergola_profile_angle the day a
# beam of sun starts to leak past the fully-tilted blades; that value is
# your real threshold.
DEFAULT_FLIP_PROFILE_THRESHOLD = 80

# Sun-exposure azimuth window for the pergola.
# Outside this window the sun is geometrically blocked by the building
# itself (east wall in the morning, west wall in the late afternoon) and
# the pergola doesn't see direct rays — the algorithm short-circuits to
# cloudy_target (diffuse light position) instead of computing a target.
# Defaults are computed lazily as face_azimuth ± 90° (= the historical
# behavior). Asymmetric to accommodate one-sided wall shadowing.
DEFAULT_SUN_AZ_HALF_WIDTH = 90  # used to derive defaults from face_az

# Summer-only blade offset (degrees), additive on top of calibration_offset.
# Lets the user shift the summer curve (both phase A and phase B) without
# affecting the winter algorithm. Positive value = more closure earlier.
DEFAULT_SUMMER_BLADE_OFFSET = 0

# Phase A is a linear ramp from (profile=0, target=phase_a_intercept) to
# (profile=flip_profile_threshold, target=100%). The cutoff formula has
# the wrong slope for real-blade physics (theoretical model over-closes
# in mid phase A); a linear model matches field observations across the
# whole range. Calibration: pick a value of phase_a_intercept that gives
# the right target at a known profile angle (e.g., the morning moment
# when first rays start passing).
DEFAULT_PHASE_A_INTERCEPT = 40

# Defaults — Operation
DEFAULT_UPDATE_INTERVAL = 5
DEFAULT_STEP_SIZE = 5
DEFAULT_DEADBAND = 2
DEFAULT_CLOUDY_TARGET = 60
DEFAULT_MIN_USEFUL_PERCENT = 9
DEFAULT_HUMIDITY_MAX = 80
DEFAULT_MIN_ELEVATION = 20
# Minutes the rain hold stays active after the rain sensor goes dry.
# 0 = trust the entity as-is (for a source that debounces itself).
DEFAULT_RAIN_CLEAR_DELAY = 10

# Defaults — Cloud detection
DEFAULT_PV_MAX_WATTS = 3000
DEFAULT_PV_SUNNY_RATIO = 0.50
DEFAULT_PV_SMOOTH_ALPHA = 0.4
DEFAULT_HYSTERESIS_DURATION = 900
DEFAULT_PV_PANEL_AZIMUTH = DEFAULT_FACE_AZIMUTH
DEFAULT_PV_PANEL_TILT = 30
DEFAULT_LUX_SUNNY_RATIO = 25000
DEFAULT_PV_OBSERVABLE_COS = 0.4
DEFAULT_LUX_AZ_MIN = 120
DEFAULT_LUX_AZ_MAX = 260

# Modes
MODE_WINTER = "Hiver"
MODE_SUMMER = "Été"
MODE_MANUAL = "Manuel"
MODES = [MODE_WINTER, MODE_SUMMER, MODE_MANUAL]

# Safety lock origins reported by the pergola controller (e.g. Somfy io).
LOCK_RAIN = "rain"
LOCK_TEMPERATURE = "temperature"
LOCK_SECURITY = "security"

# Any lock at all. Used only to tell "the controller refused this command"
# apart from "the pergola is mechanically stuck" — see
# PergolaCoordinator._async_move_and_verify.
LOCK_ORIGINS = [LOCK_RAIN, LOCK_TEMPERATURE, LOCK_SECURITY]

# Origins that make the integration close the pergola and stop moving it.
# `rain` is deliberately absent: CONF_RAIN_ENTITY is the authority on rain,
# and this sensor is too stale to trust for it — observed reporting `rain`
# minutes *after* a shower ended, and holding it ~16 min past the rain
# sensor going dry. Treating that as a block could wedge the pergola for as
# long as the controller keeps the value stuck.
LOCK_CLOSING_ORIGINS = (LOCK_TEMPERATURE, LOCK_SECURITY)

# Platforms
PLATFORMS = ["sensor", "binary_sensor", "select", "button"]
