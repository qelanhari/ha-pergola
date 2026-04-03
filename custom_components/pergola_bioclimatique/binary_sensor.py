"""Binary sensor platform for Pergola Bioclimatique."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIGHT_SENSOR_ENTITY, CONF_PV_POWER_ENTITY, DOMAIN
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

    has_cloud_sensor = entry.data.get(CONF_PV_POWER_ENTITY) or entry.data.get(
        CONF_LIGHT_SENSOR_ENTITY
    )
    if has_cloud_sensor:
        entities.append(PergolaSunnySensor(coordinator, entry))

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


class PergolaMovementProblemSensor(PergolaBaseBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "movement_problem")

    @property
    def is_on(self) -> bool:
        return not self.coordinator.movement_ok
