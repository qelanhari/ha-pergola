"""Config flow for Pergola Bioclimatique integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

# Well-known Sun integration entity IDs
SUN_AZIMUTH_ENTITY = "sensor.sun_solar_azimuth"
SUN_ELEVATION_ENTITY = "sensor.sun_solar_elevation"

# Transient UI marker (never persisted) — when the user ticks this in a basic
# form, the flow transitions to the matching *_advanced sub-step instead of
# silently writing defaults.
CONF_ADVANCED = "advanced"

from .const import (
    CONF_BLADE_PITCH_RATIO,
    CONF_CALIBRATION_OFFSET,
    CONF_CLOUDY_TARGET,
    CONF_COVER_ENTITY,
    CONF_DEADBAND,
    CONF_FACE_AZIMUTH,
    CONF_PERGOLA_MODEL,
    CONF_HUMIDITY_ENTITY,
    CONF_HUMIDITY_MAX,
    CONF_HYSTERESIS_DURATION,
    CONF_LIGHT_SENSOR_ENTITY,
    CONF_LUX_AZ_MAX,
    CONF_LUX_AZ_MIN,
    CONF_LUX_SUNNY_RATIO,
    CONF_MAX_OPENING_ANGLE,
    CONF_MIN_ELEVATION,
    CONF_MIN_USEFUL_PERCENT,
    CONF_PRIORITY_LOCK_ENTITY,
    CONF_PRIORITY_LOCK_TIMER_ENTITY,
    CONF_PV_MAX_WATTS,
    CONF_PV_OBSERVABLE_COS,
    CONF_PV_PANEL_AZIMUTH,
    CONF_PV_PANEL_TILT,
    CONF_PV_POWER_ENTITY,
    CONF_PV_SMOOTH_ALPHA,
    CONF_PV_SUNNY_RATIO,
    CONF_RAIN_CLEAR_DELAY,
    CONF_RAIN_ENTITY,
    CONF_FLIP_PROFILE_THRESHOLD,
    CONF_PHASE_A_INTERCEPT,
    CONF_STEP_SIZE,
    CONF_SUMMER_BLADE_OFFSET,
    CONF_SUN_AZ_MAX,
    CONF_SUN_AZ_MIN,
    CONF_SUN_AZIMUTH_ENTITY,
    CONF_SUN_ELEVATION_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BLADE_PITCH_RATIO,
    DEFAULT_CALIBRATION_OFFSET,
    DEFAULT_CLOUDY_TARGET,
    DEFAULT_DEADBAND,
    DEFAULT_FACE_AZIMUTH,
    DEFAULT_PERGOLA_MODEL,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_HYSTERESIS_DURATION,
    DEFAULT_LUX_AZ_MAX,
    DEFAULT_LUX_AZ_MIN,
    DEFAULT_LUX_SUNNY_RATIO,
    DEFAULT_MAX_OPENING_ANGLE,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_MIN_USEFUL_PERCENT,
    DEFAULT_PV_MAX_WATTS,
    DEFAULT_PV_OBSERVABLE_COS,
    DEFAULT_PV_PANEL_AZIMUTH,
    DEFAULT_PV_PANEL_TILT,
    DEFAULT_PV_SMOOTH_ALPHA,
    DEFAULT_PV_SUNNY_RATIO,
    DEFAULT_RAIN_CLEAR_DELAY,
    DEFAULT_FLIP_PROFILE_THRESHOLD,
    DEFAULT_PHASE_A_INTERCEPT,
    DEFAULT_SUMMER_BLADE_OFFSET,
    DEFAULT_SUN_AZ_HALF_WIDTH,
    DEFAULT_STEP_SIZE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .presets import get_preset_values, model_choices


# Geometry fields that are exposed in the advanced sub-step (everything
# except face_azimuth, which is the only basic field).
_GEOMETRY_ADVANCED_FIELDS: tuple[str, ...] = (
    CONF_MAX_OPENING_ANGLE,
    CONF_CALIBRATION_OFFSET,
    CONF_BLADE_PITCH_RATIO,
    CONF_FLIP_PROFILE_THRESHOLD,
    CONF_SUMMER_BLADE_OFFSET,
    CONF_PHASE_A_INTERCEPT,
    CONF_SUN_AZ_MIN,
    CONF_SUN_AZ_MAX,
)

# Cloud detection fields exposed in the advanced sub-step (everything except
# pv_max_watts, the only basic field).
_CLOUD_ADVANCED_FIELDS: tuple[str, ...] = (
    CONF_PV_PANEL_AZIMUTH,
    CONF_PV_PANEL_TILT,
    CONF_PV_SUNNY_RATIO,
    CONF_PV_SMOOTH_ALPHA,
    CONF_HYSTERESIS_DURATION,
    CONF_LUX_SUNNY_RATIO,
    CONF_PV_OBSERVABLE_COS,
    CONF_LUX_AZ_MIN,
    CONF_LUX_AZ_MAX,
)


def _geometry_defaults(face_azimuth: float) -> dict[str, Any]:
    """Return the full default dict for the geometry step.

    `sun_az_min` / `sun_az_max` are derived from `face_azimuth` to preserve
    historical behavior (window = face ± 90°).
    """
    return {
        CONF_MAX_OPENING_ANGLE: DEFAULT_MAX_OPENING_ANGLE,
        CONF_CALIBRATION_OFFSET: DEFAULT_CALIBRATION_OFFSET,
        CONF_BLADE_PITCH_RATIO: DEFAULT_BLADE_PITCH_RATIO,
        CONF_FLIP_PROFILE_THRESHOLD: DEFAULT_FLIP_PROFILE_THRESHOLD,
        CONF_SUMMER_BLADE_OFFSET: DEFAULT_SUMMER_BLADE_OFFSET,
        CONF_PHASE_A_INTERCEPT: DEFAULT_PHASE_A_INTERCEPT,
        CONF_SUN_AZ_MIN: face_azimuth - DEFAULT_SUN_AZ_HALF_WIDTH,
        CONF_SUN_AZ_MAX: face_azimuth + DEFAULT_SUN_AZ_HALF_WIDTH,
    }


def _cloud_defaults(face_azimuth: float) -> dict[str, Any]:
    """Return the full default dict for the cloud-detection step.

    `pv_panel_azimuth` defaults to `face_azimuth` (most installs have the PV
    panels on the same roof slope as the pergola).
    """
    return {
        CONF_PV_PANEL_AZIMUTH: face_azimuth,
        CONF_PV_PANEL_TILT: DEFAULT_PV_PANEL_TILT,
        CONF_PV_SUNNY_RATIO: DEFAULT_PV_SUNNY_RATIO,
        CONF_PV_SMOOTH_ALPHA: DEFAULT_PV_SMOOTH_ALPHA,
        CONF_HYSTERESIS_DURATION: DEFAULT_HYSTERESIS_DURATION,
        CONF_LUX_SUNNY_RATIO: DEFAULT_LUX_SUNNY_RATIO,
        CONF_PV_OBSERVABLE_COS: DEFAULT_PV_OBSERVABLE_COS,
        CONF_LUX_AZ_MIN: DEFAULT_LUX_AZ_MIN,
        CONF_LUX_AZ_MAX: DEFAULT_LUX_AZ_MAX,
    }


def _geometry_has_non_defaults(values: dict[str, Any]) -> bool:
    """True if any geometry advanced field differs from its default.

    Used by the Options flow to decide whether to open in basic or advanced
    view. `sun_az_min` / `sun_az_max` are compared against the value derived
    from the current `face_azimuth`, not against a hard-coded default.
    """
    face_az = values.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
    defaults = _geometry_defaults(face_az)
    for key in _GEOMETRY_ADVANCED_FIELDS:
        if key in values and values[key] != defaults[key]:
            return True
    return False


def _cloud_has_non_defaults(values: dict[str, Any]) -> bool:
    """True if any cloud advanced field differs from its default."""
    face_az = values.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
    defaults = _cloud_defaults(face_az)
    for key in _CLOUD_ADVANCED_FIELDS:
        if key in values and values[key] != defaults[key]:
            return True
    return False


# Every entity key the flows can set. Also the authoritative list the
# Options flow rewrites wholesale, so clearing a field actually sticks
# (see PergolaBioclimatiqueOptionsFlow.async_step_entities).
ENTITY_KEYS = (
    CONF_COVER_ENTITY,
    CONF_SUN_AZIMUTH_ENTITY,
    CONF_SUN_ELEVATION_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_LIGHT_SENSOR_ENTITY,
    CONF_HUMIDITY_ENTITY,
    CONF_RAIN_ENTITY,
    CONF_PRIORITY_LOCK_ENTITY,
    CONF_PRIORITY_LOCK_TIMER_ENTITY,
)

# The rain source is any on/off entity. Deliberately no device_class filter:
# a rain contact wired to a Shelly input reports device_class "power", so
# filtering on "moisture" would hide the very sensor this is for.
RAIN_ENTITY_DOMAINS = ["binary_sensor", "input_boolean", "switch"]


def _entity_schema(
    sun_defaults: dict[str, str] | None = None,
    current: dict[str, Any] | None = None,
    include_name: bool = True,
) -> vol.Schema:
    """Entity selection form, shared by the install and Options flows.

    Install flow passes ``sun_defaults`` to pre-fill the Sun integration
    entities. The Options flow passes ``current`` to pre-fill every field
    from the stored entry, and ``include_name=False`` (renaming the entry
    isn't offered there). Options pre-fill uses ``suggested_value`` rather
    than ``default`` so a field the user clears round-trips as empty
    instead of snapping back to the stored value.
    """
    sd = sun_defaults or {}
    cur = current or {}

    def _suggest(key: str) -> dict[str, Any]:
        value = cur.get(key)
        if not value:
            return {}
        return {"description": {"suggested_value": value}}

    schema: dict[vol.Marker, Any] = {}
    if include_name:
        schema[vol.Required(CONF_NAME, default="Pergola")] = str
    schema[vol.Required(CONF_COVER_ENTITY, **_suggest(CONF_COVER_ENTITY))] = (
        EntitySelector(EntitySelectorConfig(domain="cover"))
    )

    # Sun entities: pre-fill from the stored entry, else if Sun detected
    for key in (CONF_SUN_AZIMUTH_ENTITY, CONF_SUN_ELEVATION_ENTITY):
        if key in cur:
            marker = vol.Required(key, **_suggest(key))
        elif key in sd:
            marker = vol.Required(key, default=sd[key])
        else:
            marker = vol.Required(key)
        schema[marker] = EntitySelector(EntitySelectorConfig(domain="sensor"))

    for key in (
        CONF_PV_POWER_ENTITY,
        CONF_LIGHT_SENSOR_ENTITY,
        CONF_HUMIDITY_ENTITY,
    ):
        schema[vol.Optional(key, **_suggest(key))] = EntitySelector(
            EntitySelectorConfig(domain="sensor")
        )

    schema[vol.Optional(CONF_RAIN_ENTITY, **_suggest(CONF_RAIN_ENTITY))] = (
        EntitySelector(EntitySelectorConfig(domain=RAIN_ENTITY_DOMAINS))
    )

    for key in (CONF_PRIORITY_LOCK_ENTITY, CONF_PRIORITY_LOCK_TIMER_ENTITY):
        schema[vol.Optional(key, **_suggest(key))] = EntitySelector(
            EntitySelectorConfig(domain="sensor")
        )

    return vol.Schema(schema)


def _geometry_basic_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 2 (basic): pergola model dropdown + face_azimuth + advanced toggle."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_PERGOLA_MODEL,
                default=d.get(CONF_PERGOLA_MODEL, DEFAULT_PERGOLA_MODEL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=model_choices(),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_FACE_AZIMUTH,
                default=d.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_ADVANCED,
                default=d.get(CONF_ADVANCED, False),
            ): BooleanSelector(),
        }
    )


def _geometry_advanced_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 2 (advanced): every geometry knob. face_azimuth is included here too
    so the user can fine-tune the bearing alongside the rest."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_FACE_AZIMUTH,
                default=d.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_MAX_OPENING_ANGLE,
                default=d.get(CONF_MAX_OPENING_ANGLE, DEFAULT_MAX_OPENING_ANGLE),
            ): NumberSelector(
                NumberSelectorConfig(min=90, max=180, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_CALIBRATION_OFFSET,
                default=d.get(CONF_CALIBRATION_OFFSET, DEFAULT_CALIBRATION_OFFSET),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-30, max=30, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_BLADE_PITCH_RATIO,
                default=d.get(CONF_BLADE_PITCH_RATIO, DEFAULT_BLADE_PITCH_RATIO),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.5, max=1.2, step=0.01, mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FLIP_PROFILE_THRESHOLD,
                default=d.get(
                    CONF_FLIP_PROFILE_THRESHOLD,
                    DEFAULT_FLIP_PROFILE_THRESHOLD,
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=60, max=90, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_SUMMER_BLADE_OFFSET,
                default=d.get(
                    CONF_SUMMER_BLADE_OFFSET, DEFAULT_SUMMER_BLADE_OFFSET
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-30, max=30, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_PHASE_A_INTERCEPT,
                default=d.get(
                    CONF_PHASE_A_INTERCEPT, DEFAULT_PHASE_A_INTERCEPT
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=80, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_SUN_AZ_MIN,
                default=d.get(
                    CONF_SUN_AZ_MIN,
                    d.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
                    - DEFAULT_SUN_AZ_HALF_WIDTH,
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_SUN_AZ_MAX,
                default=d.get(
                    CONF_SUN_AZ_MAX,
                    d.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
                    + DEFAULT_SUN_AZ_HALF_WIDTH,
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
        }
    )


def _operation_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 3: Operation parameters."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=d.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=30, step=1, mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(
                CONF_STEP_SIZE,
                default=d.get(CONF_STEP_SIZE, DEFAULT_STEP_SIZE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=10, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_DEADBAND,
                default=d.get(CONF_DEADBAND, DEFAULT_DEADBAND),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1, max=10, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_CLOUDY_TARGET,
                default=d.get(CONF_CLOUDY_TARGET, DEFAULT_CLOUDY_TARGET),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=100, step=5, mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_MIN_USEFUL_PERCENT,
                default=d.get(CONF_MIN_USEFUL_PERCENT, DEFAULT_MIN_USEFUL_PERCENT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=30, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_HUMIDITY_MAX,
                default=d.get(CONF_HUMIDITY_MAX, DEFAULT_HUMIDITY_MAX),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=50, max=100, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_MIN_ELEVATION,
                default=d.get(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=5, max=40, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_RAIN_CLEAR_DELAY,
                default=d.get(CONF_RAIN_CLEAR_DELAY, DEFAULT_RAIN_CLEAR_DELAY),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=60, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
        }
    )


def _cloud_basic_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 4 (basic): just pv_max_watts + advanced toggle."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_PV_MAX_WATTS,
                default=d.get(CONF_PV_MAX_WATTS, DEFAULT_PV_MAX_WATTS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=100, max=20000, step=100, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="W",
                )
            ),
            vol.Required(
                CONF_ADVANCED,
                default=d.get(CONF_ADVANCED, False),
            ): BooleanSelector(),
        }
    )


def _cloud_advanced_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 4 (advanced): every cloud-detection knob."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_PV_MAX_WATTS,
                default=d.get(CONF_PV_MAX_WATTS, DEFAULT_PV_MAX_WATTS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=100, max=20000, step=100, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="W",
                )
            ),
            vol.Required(
                CONF_PV_PANEL_AZIMUTH,
                default=d.get(CONF_PV_PANEL_AZIMUTH, DEFAULT_PV_PANEL_AZIMUTH),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_PV_PANEL_TILT,
                default=d.get(CONF_PV_PANEL_TILT, DEFAULT_PV_PANEL_TILT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=90, step=1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_PV_SUNNY_RATIO,
                default=d.get(CONF_PV_SUNNY_RATIO, DEFAULT_PV_SUNNY_RATIO),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1, max=1.0, step=0.05, mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_PV_SMOOTH_ALPHA,
                default=d.get(CONF_PV_SMOOTH_ALPHA, DEFAULT_PV_SMOOTH_ALPHA),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1, max=0.9, step=0.05, mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_HYSTERESIS_DURATION,
                default=d.get(CONF_HYSTERESIS_DURATION, DEFAULT_HYSTERESIS_DURATION),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=60, max=3600, step=60, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Required(
                CONF_LUX_SUNNY_RATIO,
                default=d.get(CONF_LUX_SUNNY_RATIO, DEFAULT_LUX_SUNNY_RATIO),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1000, max=100000, step=500,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="lx",
                )
            ),
            vol.Required(
                CONF_PV_OBSERVABLE_COS,
                default=d.get(CONF_PV_OBSERVABLE_COS, DEFAULT_PV_OBSERVABLE_COS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.0, max=0.9, step=0.05,
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(
                CONF_LUX_AZ_MIN,
                default=d.get(CONF_LUX_AZ_MIN, DEFAULT_LUX_AZ_MIN),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=5, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
            vol.Required(
                CONF_LUX_AZ_MAX,
                default=d.get(CONF_LUX_AZ_MAX, DEFAULT_LUX_AZ_MAX),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=360, step=5, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="°",
                )
            ),
        }
    )


class PergolaBioclimatiqueConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pergola Bioclimatique."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _sun_integration_available(self) -> bool:
        """Check if the Sun integration is loaded and provides required entities."""
        azim = self.hass.states.get(SUN_AZIMUTH_ENTITY)
        elev = self.hass.states.get(SUN_ELEVATION_ENTITY)
        return azim is not None and elev is not None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 1: Entity selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            # Validate that selected sun entities actually exist
            for key in (CONF_SUN_AZIMUTH_ENTITY, CONF_SUN_ELEVATION_ENTITY):
                entity_id = user_input.get(key)
                if entity_id and self.hass.states.get(entity_id) is None:
                    errors[key] = "entity_not_found"

            if not errors:
                return await self.async_step_geometry()

        # Auto-detect Sun integration entities for defaults
        sun_defaults: dict[str, str] = {}
        if self._sun_integration_available():
            sun_defaults[CONF_SUN_AZIMUTH_ENTITY] = SUN_AZIMUTH_ENTITY
            sun_defaults[CONF_SUN_ELEVATION_ENTITY] = SUN_ELEVATION_ENTITY

        return self.async_show_form(
            step_id="user",
            data_schema=_entity_schema(sun_defaults),
            errors=errors,
            description_placeholders={
                "sun_status": "detected" if sun_defaults else "not_found"
            },
        )

    async def async_step_geometry(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 2 (basic): pergola model + face azimuth + advanced toggle.

        With advanced off (default), fill every other geometry field with its
        default value derived from face_azimuth, then overlay any preset
        values from the chosen pergola model. Stored entry is identical to
        what the legacy flow produced when the user left every field at
        default AND picked "Custom / Other".
        """
        if user_input is not None:
            wants_advanced = user_input.pop(CONF_ADVANCED, False)
            self._data.update(user_input)
            face_az = self._data.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
            model_id = self._data.get(CONF_PERGOLA_MODEL, DEFAULT_PERGOLA_MODEL)
            preset_values = get_preset_values(model_id)
            if wants_advanced:
                # Stash preset values so the advanced form pre-fills them as
                # defaults the user can review and edit.
                self._data.update(preset_values)
                return await self.async_step_geometry_advanced()
            # Apply geometry defaults first (face-dependent), then overlay the
            # preset's spec-sheet values so the model's published numbers win.
            self._data.update(_geometry_defaults(face_az))
            self._data.update(preset_values)
            return await self.async_step_operation()

        return self.async_show_form(
            step_id="geometry",
            data_schema=_geometry_basic_schema(),
        )

    async def async_step_geometry_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 2 (advanced): every geometry knob exposed."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_operation()

        return self.async_show_form(
            step_id="geometry_advanced",
            data_schema=_geometry_advanced_schema(self._data),
        )

    async def async_step_operation(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 3: Operation parameters."""
        if user_input is not None:
            self._data.update(user_input)
            # Skip cloud detection step if no PV/light sensor configured
            if not self._data.get(CONF_PV_POWER_ENTITY) and not self._data.get(
                CONF_LIGHT_SENSOR_ENTITY
            ):
                return self._create_entry()
            return await self.async_step_cloud_detection()

        return self.async_show_form(
            step_id="operation",
            data_schema=_operation_schema(),
        )

    async def async_step_cloud_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 4 (basic): pv_max_watts + advanced toggle."""
        if user_input is not None:
            wants_advanced = user_input.pop(CONF_ADVANCED, False)
            self._data.update(user_input)
            if wants_advanced:
                return await self.async_step_cloud_detection_advanced()
            face_az = self._data.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
            self._data.update(_cloud_defaults(face_az))
            return self._create_entry()

        return self.async_show_form(
            step_id="cloud_detection",
            data_schema=_cloud_basic_schema(),
        )

    async def async_step_cloud_detection_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 4 (advanced): every cloud-detection knob."""
        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        return self.async_show_form(
            step_id="cloud_detection_advanced",
            data_schema=_cloud_advanced_schema(self._data),
        )

    def _create_entry(self) -> Any:
        name = self._data.pop(CONF_NAME, "Pergola")
        return self.async_create_entry(title=name, data=self._data)

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> PergolaBioclimatiqueOptionsFlow:
        return PergolaBioclimatiqueOptionsFlow(config_entry)


class PergolaBioclimatiqueOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle options flow for reconfiguring parameters at runtime.

    Existing entries that already contain non-default values are opened
    straight in the advanced view for that step, so the user's current setup
    is visible and editable instead of being silently re-defaulted.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__(config_entry)
        self._options: dict[str, Any] = dict(config_entry.options)

    def _current(self) -> dict[str, Any]:
        """Merged data+options snapshot for default population."""
        return {**self.config_entry.data, **self.config_entry.options, **self._options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Entity selection — the first Options step."""
        return await self.async_step_entities(user_input)

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Reconfigure the source entities without recreating the entry."""
        if user_input is not None:
            # Write every entity key explicitly, including the ones the
            # user cleared: Home Assistant omits empty optional fields from
            # user_input, and the coordinator falls back to entry.data, so
            # a bare update() would silently resurrect a cleared entity.
            for key in ENTITY_KEYS:
                self._options[key] = user_input.get(key)
            return await self.async_step_geometry()

        return self.async_show_form(
            step_id="entities",
            data_schema=_entity_schema(
                current=self._current(), include_name=False
            ),
        )

    async def async_step_geometry(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Geometry step — basic by default; advanced if any field was customized."""
        if _geometry_has_non_defaults(self._current()):
            return await self.async_step_geometry_advanced()
        return await self.async_step_geometry_basic(user_input)

    async def async_step_geometry_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            wants_advanced = user_input.pop(CONF_ADVANCED, False)
            self._options.update(user_input)
            face_az = self._options.get(
                CONF_FACE_AZIMUTH,
                self.config_entry.data.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH),
            )
            model_id = self._options.get(
                CONF_PERGOLA_MODEL,
                self.config_entry.data.get(CONF_PERGOLA_MODEL, DEFAULT_PERGOLA_MODEL),
            )
            preset_values = get_preset_values(model_id)
            if wants_advanced:
                self._options.update(preset_values)
                return await self.async_step_geometry_advanced()
            self._options.update(_geometry_defaults(face_az))
            self._options.update(preset_values)
            return await self.async_step_operation()

        return self.async_show_form(
            step_id="geometry_basic",
            data_schema=_geometry_basic_schema(self._current()),
        )

    async def async_step_geometry_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_operation()

        return self.async_show_form(
            step_id="geometry_advanced",
            data_schema=_geometry_advanced_schema(self._current()),
        )

    async def async_step_operation(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._options.update(user_input)
            # Read merged, not from entry.data: the entities step earlier in
            # this same flow may have just added or removed a cloud sensor.
            current = self._current()
            has_cloud_sensor = current.get(CONF_PV_POWER_ENTITY) or current.get(
                CONF_LIGHT_SENSOR_ENTITY
            )
            if not has_cloud_sensor:
                return self.async_create_entry(title="", data=self._options)
            if _cloud_has_non_defaults(self._current()):
                return await self.async_step_cloud_detection_advanced()
            return await self.async_step_cloud_detection_basic()

        return self.async_show_form(
            step_id="operation",
            data_schema=_operation_schema(self._current()),
        )

    async def async_step_cloud_detection_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            wants_advanced = user_input.pop(CONF_ADVANCED, False)
            self._options.update(user_input)
            if wants_advanced:
                return await self.async_step_cloud_detection_advanced()
            face_az = self._options.get(
                CONF_FACE_AZIMUTH,
                self.config_entry.data.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH),
            )
            self._options.update(_cloud_defaults(face_az))
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="cloud_detection_basic",
            data_schema=_cloud_basic_schema(self._current()),
        )

    async def async_step_cloud_detection_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="cloud_detection_advanced",
            data_schema=_cloud_advanced_schema(self._current()),
        )
