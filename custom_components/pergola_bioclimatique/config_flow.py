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

from .const import (
    CONF_BLADE_PITCH_RATIO,
    CONF_CALIBRATION_OFFSET,
    CONF_CLOUDY_TARGET,
    CONF_COVER_ENTITY,
    CONF_DEADBAND,
    CONF_FACE_AZIMUTH,
    CONF_HUMIDITY_ENTITY,
    CONF_HUMIDITY_MAX,
    CONF_HYSTERESIS_DURATION,
    CONF_LIGHT_SENSOR_ENTITY,
    CONF_MAX_OPENING_ANGLE,
    CONF_MIN_ELEVATION,
    CONF_MIN_USEFUL_PERCENT,
    CONF_PRIORITY_LOCK_ENTITY,
    CONF_PRIORITY_LOCK_TIMER_ENTITY,
    CONF_PV_MAX_WATTS,
    CONF_PV_PANEL_AZIMUTH,
    CONF_PV_PANEL_TILT,
    CONF_PV_POWER_ENTITY,
    CONF_PV_SMOOTH_ALPHA,
    CONF_PV_SUNNY_RATIO,
    CONF_STEP_SIZE,
    CONF_SUMMER_MODE,
    CONF_SUMMER_SAFETY_MARGIN,
    CONF_SUN_AZIMUTH_ENTITY,
    CONF_SUN_ELEVATION_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BLADE_PITCH_RATIO,
    DEFAULT_CALIBRATION_OFFSET,
    DEFAULT_CLOUDY_TARGET,
    DEFAULT_DEADBAND,
    DEFAULT_FACE_AZIMUTH,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_HYSTERESIS_DURATION,
    DEFAULT_MAX_OPENING_ANGLE,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_MIN_USEFUL_PERCENT,
    DEFAULT_PV_MAX_WATTS,
    DEFAULT_PV_PANEL_AZIMUTH,
    DEFAULT_PV_PANEL_TILT,
    DEFAULT_PV_SMOOTH_ALPHA,
    DEFAULT_PV_SUNNY_RATIO,
    DEFAULT_STEP_SIZE,
    DEFAULT_SUMMER_MODE,
    DEFAULT_SUMMER_SAFETY_MARGIN,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SUMMER_MODES,
)


def _entity_schema(sun_defaults: dict[str, str] | None = None) -> vol.Schema:
    """Step 1: Entity selection. Auto-fills sun entities if detected."""
    sd = sun_defaults or {}
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_NAME, default="Pergola"): str,
        vol.Required(CONF_COVER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="cover")
        ),
    }

    # Sun entities: pre-fill if Sun integration detected
    if CONF_SUN_AZIMUTH_ENTITY in sd:
        schema[vol.Required(
            CONF_SUN_AZIMUTH_ENTITY, default=sd[CONF_SUN_AZIMUTH_ENTITY]
        )] = EntitySelector(EntitySelectorConfig(domain="sensor"))
    else:
        schema[vol.Required(CONF_SUN_AZIMUTH_ENTITY)] = EntitySelector(
            EntitySelectorConfig(domain="sensor")
        )

    if CONF_SUN_ELEVATION_ENTITY in sd:
        schema[vol.Required(
            CONF_SUN_ELEVATION_ENTITY, default=sd[CONF_SUN_ELEVATION_ENTITY]
        )] = EntitySelector(EntitySelectorConfig(domain="sensor"))
    else:
        schema[vol.Required(CONF_SUN_ELEVATION_ENTITY)] = EntitySelector(
            EntitySelectorConfig(domain="sensor")
        )

    schema.update({
        vol.Optional(CONF_PV_POWER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_LIGHT_SENSOR_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_HUMIDITY_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_PRIORITY_LOCK_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_PRIORITY_LOCK_TIMER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
    })
    return vol.Schema(schema)


def _geometry_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 2: Geometry parameters."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_FACE_AZIMUTH,
                default=d.get(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=360, step=1, mode=NumberSelectorMode.BOX)
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
                CONF_SUMMER_SAFETY_MARGIN,
                default=d.get(CONF_SUMMER_SAFETY_MARGIN, DEFAULT_SUMMER_SAFETY_MARGIN),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_SUMMER_MODE,
                default=d.get(CONF_SUMMER_MODE, DEFAULT_SUMMER_MODE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SUMMER_MODES,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_SUMMER_MODE,
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
        }
    )


def _cloud_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Step 4: Cloud detection parameters."""
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
        """Step 2: Geometry parameters."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_operation()

        return self.async_show_form(
            step_id="geometry",
            data_schema=_geometry_schema(),
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
        """Step 4: Cloud detection parameters."""
        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        return self.async_show_form(
            step_id="cloud_detection",
            data_schema=_cloud_schema(),
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
    """Handle options flow for reconfiguring parameters at runtime."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__(config_entry)
        self._options: dict[str, Any] = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Start options flow with geometry step."""
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_operation()

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_geometry_schema(current),
        )

    async def async_step_operation(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._options.update(user_input)
            has_cloud_sensor = self.config_entry.data.get(
                CONF_PV_POWER_ENTITY
            ) or self.config_entry.data.get(CONF_LIGHT_SENSOR_ENTITY)
            if not has_cloud_sensor:
                return self.async_create_entry(title="", data=self._options)
            return await self.async_step_cloud_detection()

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="operation",
            data_schema=_operation_schema(current),
        )

    async def async_step_cloud_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="cloud_detection",
            data_schema=_cloud_schema(current),
        )
