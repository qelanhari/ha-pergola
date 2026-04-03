"""Sensor platform for Pergola Bioclimatique."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE, PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PV_POWER_ENTITY, CONF_LIGHT_SENSOR_ENTITY, DOMAIN
from .coordinator import PergolaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PergolaCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        PergolaProfileAngleSensor(coordinator, entry),
        PergolaSolarTargetSensor(coordinator, entry),
        PergolaFinalTargetSensor(coordinator, entry),
    ]

    has_cloud_sensor = entry.data.get(CONF_PV_POWER_ENTITY) or entry.data.get(
        CONF_LIGHT_SENSOR_ENTITY
    )
    if has_cloud_sensor:
        entities.append(PergolaPvSmoothSensor(coordinator, entry))

    async_add_entities(entities)


class PergolaBaseSensor(CoordinatorEntity[PergolaCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PergolaCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Pergola Bioclimatique",
            model="Custom Integration",
        )


class PergolaProfileAngleSensor(PergolaBaseSensor):
    _attr_native_unit_of_measurement = DEGREE
    _attr_icon = "mdi:angle-acute"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "profile_angle", "Angle de profil")

    @property
    def native_value(self) -> float:
        return self.coordinator.profile_angle


class PergolaSolarTargetSensor(PergolaBaseSensor):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:sun-compass"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "solar_target", "Cible solaire")

    @property
    def native_value(self) -> float:
        return self.coordinator.solar_target


class PergolaFinalTargetSensor(PergolaBaseSensor):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:target"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "final_target", "Cible finale")

    @property
    def native_value(self) -> float:
        return self.coordinator.final_target


class PergolaPvSmoothSensor(PergolaBaseSensor):
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pv_smooth", "PV lissé")

    @property
    def native_value(self) -> float:
        return self.coordinator.pv_smooth
