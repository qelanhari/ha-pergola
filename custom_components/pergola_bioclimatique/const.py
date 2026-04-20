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
CONF_SUMMER_SAFETY_MARGIN = "summer_safety_margin"
CONF_SUMMER_MODE = "summer_mode"
CONF_BLADE_PITCH_RATIO = "blade_pitch_ratio"

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

# Defaults — Geometry
DEFAULT_FACE_AZIMUTH = 130
DEFAULT_MAX_OPENING_ANGLE = 135
DEFAULT_CALIBRATION_OFFSET = -10
DEFAULT_SUMMER_SAFETY_MARGIN = 10
DEFAULT_BLADE_PITCH_RATIO = 0.92

# Summer algorithms
SUMMER_MODE_PERPENDICULAR = "perpendicular"
SUMMER_MODE_CUTOFF = "cutoff"
SUMMER_MODES = [SUMMER_MODE_PERPENDICULAR, SUMMER_MODE_CUTOFF]
DEFAULT_SUMMER_MODE = SUMMER_MODE_CUTOFF

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
DEFAULT_PV_SUNNY_RATIO = 0.70
DEFAULT_PV_SMOOTH_ALPHA = 0.4
DEFAULT_HYSTERESIS_DURATION = 900
DEFAULT_PV_PANEL_AZIMUTH = 180
DEFAULT_PV_PANEL_TILT = 30

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
