"""Binary sensor platform for Pergola Bioclimatique."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_LIGHT_SENSOR_ENTITY,
    CONF_PRESENCE_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_RAIN_ENTITY,
    DOMAIN,
    entry_value,
)
from .coordinator import PergolaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PergolaCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = [
        PergolaReadySensor(coordinator, entry),
        PergolaCalibratedTodaySensor(coordinator, entry),
        PergolaMovementProblemSensor(coordinator, entry),
    ]

    has_cloud_sensor = entry_value(entry, CONF_PV_POWER_ENTITY) or entry_value(
        entry, CONF_LIGHT_SENSOR_ENTITY
    )
    if has_cloud_sensor:
        entities.append(PergolaSunnySensor(coordinator, entry))

    if entry_value(entry, CONF_RAIN_ENTITY):
        entities.append(PergolaRainHoldSensor(coordinator, entry))

    if entry_value(entry, CONF_PRESENCE_ENTITY):
        entities.append(PergolaPresenceParkedSensor(coordinator, entry))

    async_add_entities(entities)


class PergolaBaseBinarySensor(
    CoordinatorEntity[PergolaCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PergolaCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Pergola Bioclimatique",
            model="Custom Integration",
        )


class PergolaSunnySensor(PergolaBaseBinarySensor):
    _attr_icon = "mdi:weather-sunny"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "is_sunny")

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_sunny


class PergolaReadySensor(PergolaBaseBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:check-circle"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ready")

    @property
    def is_on(self) -> bool:
        return self.coordinator.pergola_ready


class PergolaCalibratedTodaySensor(PergolaBaseBinarySensor):
    _attr_icon = "mdi:calibrate"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "calibrated_today")

    @property
    def is_on(self) -> bool:
        return self.coordinator.calibrated_today


class PergolaRainHoldSensor(PergolaBaseBinarySensor):
    """On while rain is suppressing all movement.

    The one place a user can see *why* the pergola stopped tracking —
    previously an active hold was only visible in the debug log.
    """

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_icon = "mdi:weather-pouring"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "rain_hold")

    @property
    def is_on(self) -> bool:
        return self.coordinator.rain_hold


class PergolaPresenceParkedSensor(PergolaBaseBinarySensor):
    """On while an empty house is holding the pergola closed.

    Not the same as "nobody home": it only lights once the pergola has
    actually parked at 0%, which happens at the next close-through-0% after
    everyone leaves.
    """

    _attr_icon = "mdi:home-export-outline"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "presence_parked")

    @property
    def is_on(self) -> bool:
        return self.coordinator.presence_parked

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"away": self.coordinator.presence_away}


class PergolaMovementProblemSensor(PergolaBaseBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "movement_problem")

    @property
    def is_on(self) -> bool:
        return not self.coordinator.movement_ok

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose any reported lock, so a refused command is legible.

        A refusal no longer lights this sensor at all, but seeing the origin
        here explains why a target isn't being reached.
        """
        return {"lock_origin": self.coordinator.lock_origin or None}
