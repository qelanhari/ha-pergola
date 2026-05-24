"""Constants for the Pergola Bioclimatique integration."""

DOMAIN = "pergola_bioclimatique"

# Config keys — Step 1: Entity selection
CONF_COVER_ENTITY = "cover_entity"
CONF_SUN_AZIMUTH_ENTITY = "sun_azimuth_entity"
CONF_SUN_ELEVATION_ENTITY = "sun_elevation_entity"
CONF_PV_POWER_ENTITY = "pv_power_entity"
CONF_LIGHT_SENSOR_ENTITY = "light_sensor_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_PRIORITY_LOCK_ENTITY = "priority_lock_entity"
CONF_PRIORITY_LOCK_TIMER_ENTITY = "priority_lock_timer_entity"

# Config keys — Step 2: Geometry
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

# Safety lock origins
LOCK_RAIN = "rain"
LOCK_TEMPERATURE = "temperature"
LOCK_SECURITY = "security"
LOCK_ORIGINS = [LOCK_RAIN, LOCK_TEMPERATURE, LOCK_SECURITY]

# Platforms
PLATFORMS = ["sensor", "binary_sensor", "select", "button"]
