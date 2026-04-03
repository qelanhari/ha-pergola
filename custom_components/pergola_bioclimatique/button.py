"""Button platform for Pergola Bioclimatique."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PergolaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PergolaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PergolaRecalibrateButton(coordinator, entry),
        PergolaRefreshButton(coordinator, entry),
    ])


class PergolaBaseButton(CoordinatorEntity[PergolaCoordinator], ButtonEntity):
    _attr_has_entity_name = True

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


class PergolaRecalibrateButton(PergolaBaseButton):
    _attr_icon = "mdi:calibrate"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "recalibrate", "Recalibrer")

    async def async_press(self) -> None:
        await self.coordinator.async_force_recalibrate()


class PergolaRefreshButton(PergolaBaseButton):
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: PergolaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "refresh_target", "Recalculer la cible")

    async def async_press(self) -> None:
        await self.coordinator.async_force_refresh()
