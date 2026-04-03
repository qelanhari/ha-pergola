"""DataUpdateCoordinator for Pergola Bioclimatique."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import solar
from .const import (
    CONF_CALIBRATION_ELEVATION,
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
    CONF_PV_POWER_ENTITY,
    CONF_PV_SMOOTH_ALPHA,
    CONF_PV_SUNNY_RATIO,
    CONF_STEP_SIZE,
    CONF_SUMMER_SAFETY_MARGIN,
    CONF_SUN_AZIMUTH_ENTITY,
    CONF_SUN_ELEVATION_ENTITY,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    LOCK_ORIGINS,
    LOCK_RAIN,
    MODE_MANUAL,
    MODE_SUMMER,
    MODE_WINTER,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.state"


class PergolaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that manages the pergola bioclimatique control loop."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=self._opt(entry, CONF_UPDATE_INTERVAL, 5)
            ),
        )
        self.config_entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub_listeners: list[Any] = []

        # Internal state (replaces all helper entities)
        self._mode: str = MODE_WINTER
        self._pv_smooth: float = 0.0
        self._is_sunny: bool = False
        self._sunny_changed_at: datetime = datetime.min
        self._last_calibration: date | None = None
        self._pergola_ready: bool = False
        self._descent_calibrated: bool = False
        self._calibrating: bool = False
        self._watchdog_running: bool = False

        # Computed values exposed to sensors
        self._profile_angle: float = 0.0
        self._solar_target: float = 0.0
        self._final_target: float = 0.0

    # --- Properties for entities ---

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def pv_smooth(self) -> float:
        return self._pv_smooth

    @property
    def is_sunny(self) -> bool:
        return self._is_sunny

    @property
    def pergola_ready(self) -> bool:
        return self._pergola_ready

    @property
    def calibrated_today(self) -> bool:
        return self._last_calibration == date.today()

    @property
    def profile_angle(self) -> float:
        return self._profile_angle

    @property
    def solar_target(self) -> float:
        return self._solar_target

    @property
    def final_target(self) -> float:
        return self._final_target

    # --- Config helpers ---

    @staticmethod
    def _opt(entry: ConfigEntry, key: str, default: Any = None) -> Any:
        return entry.options.get(key, entry.data.get(key, default))

    def _cfg(self, key: str, default: Any = None) -> Any:
        return self._opt(self.config_entry, key, default)

    def _entity(self, key: str) -> str | None:
        val = self._cfg(key)
        return val if val else None

    # --- State reading helpers ---

    def _get_float(self, entity_id: str | None, default: float = 0.0) -> float:
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return default
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return default

    def _get_state(self, entity_id: str | None, default: str = "") -> str:
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return default
        return state.state

    def _get_cover_tilt(self) -> float:
        cover_id = self._entity(CONF_COVER_ENTITY)
        if not cover_id:
            return 0.0
        state = self.hass.states.get(cover_id)
        if state is None:
            return 0.0
        tilt = state.attributes.get("current_tilt_position")
        if tilt is None:
            return 0.0
        try:
            return float(tilt)
        except (ValueError, TypeError):
            return 0.0

    # --- Lifecycle ---

    async def async_setup(self) -> None:
        """Load persisted state and register listeners."""
        await self._load_state()
        self._register_listeners()

    async def async_teardown(self) -> None:
        """Unregister listeners."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    def _register_listeners(self) -> None:
        # Watchdog: listen for safety lock changes
        lock_entity = self._entity(CONF_PRIORITY_LOCK_ENTITY)
        if lock_entity:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, lock_entity, self._on_lock_change
                )
            )

        # Calibration: listen for sun elevation crossing threshold
        elev_entity = self._entity(CONF_SUN_ELEVATION_ENTITY)
        if elev_entity:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, elev_entity, self._on_elevation_change
                )
            )

        # Midnight reset
        self._unsub_listeners.append(
            async_track_time_change(
                self.hass, self._midnight_reset, hour=0, minute=0, second=0
            )
        )

    # --- Persistence ---

    async def _load_state(self) -> None:
        data = await self._store.async_load()
        if data:
            self._pv_smooth = data.get("pv_smooth", 0.0)
            self._is_sunny = data.get("is_sunny", False)
            self._mode = data.get("mode", MODE_WINTER)
            last_cal = data.get("last_calibration")
            if last_cal:
                try:
                    self._last_calibration = date.fromisoformat(last_cal)
                except ValueError:
                    self._last_calibration = None
            self._pergola_ready = data.get("pergola_ready", False)
            self._descent_calibrated = data.get("descent_calibrated", False)
            sunny_ts = data.get("sunny_changed_at")
            if sunny_ts:
                try:
                    self._sunny_changed_at = datetime.fromisoformat(sunny_ts)
                except ValueError:
                    pass

    async def _save_state(self) -> None:
        await self._store.async_save({
            "pv_smooth": self._pv_smooth,
            "is_sunny": self._is_sunny,
            "mode": self._mode,
            "last_calibration": (
                self._last_calibration.isoformat() if self._last_calibration else None
            ),
            "pergola_ready": self._pergola_ready,
            "descent_calibrated": self._descent_calibrated,
            "sunny_changed_at": self._sunny_changed_at.isoformat(),
        })

    # --- Mode control (called from SelectEntity) ---

    async def async_set_mode(self, mode: str) -> None:
        self._mode = mode
        await self._save_state()
        await self.async_request_refresh()

    # --- Main control loop (called every N minutes by DataUpdateCoordinator) ---

    async def _async_update_data(self) -> dict[str, Any]:
        """Main control loop — replaces the v3 bioclimat automation."""
        if self._mode == MODE_MANUAL:
            return self._build_data()

        azim = self._get_float(self._entity(CONF_SUN_AZIMUTH_ENTITY))
        elev = self._get_float(self._entity(CONF_SUN_ELEVATION_ENTITY))
        current_pos = self._get_cover_tilt()

        min_elev = self._cfg(CONF_MIN_ELEVATION, 5)
        if elev <= min_elev:
            return self._build_data()

        # Check humidity block
        humidity_entity = self._entity(CONF_HUMIDITY_ENTITY)
        if humidity_entity:
            humidity = self._get_float(humidity_entity)
            humidity_max = self._cfg(CONF_HUMIDITY_MAX, 80)
            if humidity >= humidity_max:
                return self._build_data()

        # Check safety lock
        lock_entity = self._entity(CONF_PRIORITY_LOCK_ENTITY)
        if lock_entity:
            lock_origin = self._get_state(lock_entity)
            if lock_origin in LOCK_ORIGINS:
                return self._build_data()

        # Solar geometry
        face_azimuth = self._cfg(CONF_FACE_AZIMUTH, 130)
        max_angle = self._cfg(CONF_MAX_OPENING_ANGLE, 135)
        offset = self._cfg(CONF_CALIBRATION_OFFSET, -10)
        step = self._cfg(CONF_STEP_SIZE, 5)
        safety = self._cfg(CONF_SUMMER_SAFETY_MARGIN, 10)
        cloudy_target = self._cfg(CONF_CLOUDY_TARGET, 60)
        min_useful = self._cfg(CONF_MIN_USEFUL_PERCENT, 9)

        self._profile_angle = solar.compute_profile_angle(elev, azim, face_azimuth)

        # Compute target based on mode
        if self._mode == MODE_WINTER:
            solar_percent = solar.compute_winter_target(
                self._profile_angle, offset, current_pos, max_angle, step
            )
        else:
            solar_percent = solar.compute_summer_target(
                self._profile_angle, offset, safety, max_angle, step
            )

        self._solar_target = solar_percent

        # Cloud detection (PV or light sensor)
        self._update_cloud_detection(azim, elev, face_azimuth)

        # Final target
        is_standby = solar_percent < min_useful
        if is_standby:
            final = cloudy_target
        elif self._is_sunny:
            final = solar_percent
        elif self._mode == MODE_WINTER:
            final = max(cloudy_target, current_pos)
        else:
            final = cloudy_target

        final = solar.quantize(final, step)
        self._final_target = final

        # Movement gating
        deadband = self._cfg(CONF_DEADBAND, 2)
        if abs(final - current_pos) <= deadband:
            return self._build_data()

        if not self._pergola_ready:
            return self._build_data()

        # Descent calibration logic
        cover_id = self._entity(CONF_COVER_ENTITY)
        if not cover_id:
            return self._build_data()

        if final > current_pos + 5:
            # Opening: reset descent flag
            self._descent_calibrated = False
        elif final < current_pos - 5 and not self._descent_calibrated:
            # Significant descent without calibration: recalibrate first
            await self.hass.services.async_call(
                "cover", "close_cover_tilt",
                target={"entity_id": cover_id},
            )
            await asyncio.sleep(45)
            new_pos = self._get_cover_tilt()
            if new_pos < 5:
                self._descent_calibrated = True
            # Continue to set final position below

        # Move pergola
        await self.hass.services.async_call(
            "cover", "set_cover_tilt_position",
            service_data={"tilt_position": int(final)},
            target={"entity_id": cover_id},
        )

        await self._save_state()
        return self._build_data()

    def _update_cloud_detection(
        self, azim: float, elev: float, face_azimuth: float
    ) -> None:
        """Update PV smoothing and sunny state with hysteresis."""
        pv_entity = self._entity(CONF_PV_POWER_ENTITY)
        light_entity = self._entity(CONF_LIGHT_SENSOR_ENTITY)

        if not pv_entity and not light_entity:
            # No cloud detection sensor: assume sunny
            self._is_sunny = True
            return

        alpha = self._cfg(CONF_PV_SMOOTH_ALPHA, 0.4)
        hysteresis = self._cfg(CONF_HYSTERESIS_DURATION, 900)

        if pv_entity:
            pv_raw = self._get_float(pv_entity)
            self._pv_smooth = solar.smooth_pv(pv_raw, self._pv_smooth, alpha)

            pv_max = self._cfg(CONF_PV_MAX_WATTS, 3000)
            ratio = self._cfg(CONF_PV_SUNNY_RATIO, 0.30)
            threshold = solar.compute_pv_threshold(
                azim, elev, face_azimuth, pv_max, ratio
            )
            sunny_now = self._pv_smooth > threshold
        else:
            # Light sensor: simple threshold (value > 400 lux = sunny)
            light_val = self._get_float(light_entity)
            self._pv_smooth = solar.smooth_pv(light_val, self._pv_smooth, alpha)
            sunny_now = self._pv_smooth > 400

        # Hysteresis: only change state if enough time has passed
        elapsed = (datetime.now() - self._sunny_changed_at).total_seconds()
        if elapsed > hysteresis:
            if sunny_now != self._is_sunny:
                self._is_sunny = sunny_now
                self._sunny_changed_at = datetime.now()

    # --- Morning calibration ---

    @callback
    def _on_elevation_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        try:
            elev = float(new_state.state)
        except (ValueError, TypeError):
            return

        threshold = self._cfg(CONF_CALIBRATION_ELEVATION, 20)
        if elev > threshold and not self._pergola_ready and not self._calibrating:
            self.hass.async_create_task(self._async_calibrate())

    async def _async_calibrate(self) -> None:
        """Morning calibration: close fully, verify, unlock."""
        lock_entity = self._entity(CONF_PRIORITY_LOCK_ENTITY)
        if lock_entity:
            lock_origin = self._get_state(lock_entity)
            if lock_origin in LOCK_ORIGINS:
                return

        cover_id = self._entity(CONF_COVER_ENTITY)
        if not cover_id:
            return

        self._calibrating = True
        try:
            today = date.today()
            if self._last_calibration != today:
                _LOGGER.info("Pergola: starting morning calibration")
                await self.hass.services.async_call(
                    "cover", "close_cover_tilt",
                    target={"entity_id": cover_id},
                )
                await asyncio.sleep(45)

                pos = self._get_cover_tilt()
                if pos >= 5:
                    _LOGGER.warning(
                        "Pergola: calibration failed, position %.1f%% (expected < 5%%)",
                        pos,
                    )
                    return

                self._last_calibration = today
                _LOGGER.info("Pergola: calibration successful")

            self._pergola_ready = True
            self._descent_calibrated = False
            await self._save_state()
            await self.async_request_refresh()
        finally:
            self._calibrating = False

    # --- Midnight reset ---

    @callback
    def _midnight_reset(self, _now: datetime) -> None:
        """Reset locks at midnight for next morning calibration."""
        self._pergola_ready = False
        self._descent_calibrated = False
        _LOGGER.info("Pergola: midnight reset — locked until morning calibration")
        self.hass.async_create_task(self._save_state())

    # --- Watchdog ---

    @callback
    def _on_lock_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        origin = new_state.state
        if origin in LOCK_ORIGINS and not self._watchdog_running:
            self.hass.async_create_task(self._async_watchdog(origin))

    async def _async_watchdog(self, initial_origin: str) -> None:
        """Safety watchdog: monitor lock state and respond."""
        self._watchdog_running = True
        cover_id = self._entity(CONF_COVER_ENTITY)
        lock_entity = self._entity(CONF_PRIORITY_LOCK_ENTITY)
        timer_entity = self._entity(CONF_PRIORITY_LOCK_TIMER_ENTITY)

        try:
            while True:
                origin = self._get_state(lock_entity)
                if origin not in LOCK_ORIGINS:
                    break

                wait_time = max(
                    60, int(self._get_float(timer_entity, 60))
                )
                await asyncio.sleep(wait_time + 5)

                if not cover_id:
                    continue

                if origin in ("temperature", "security"):
                    await self.hass.services.async_call(
                        "cover", "close_cover_tilt",
                        target={"entity_id": cover_id},
                    )
                    await asyncio.sleep(120)
                elif origin == LOCK_RAIN:
                    # Hold current position
                    current = self._get_cover_tilt()
                    await self.hass.services.async_call(
                        "cover", "set_cover_tilt_position",
                        service_data={"tilt_position": int(current)},
                        target={"entity_id": cover_id},
                    )

                await asyncio.sleep(5)

            _LOGGER.info("Pergola: safety lock cleared, resuming normal operation")
            await self.async_request_refresh()
        finally:
            self._watchdog_running = False

    # --- Data for entities ---

    def _build_data(self) -> dict[str, Any]:
        return {
            "profile_angle": round(self._profile_angle, 1),
            "solar_target": round(self._solar_target, 1),
            "final_target": round(self._final_target, 1),
            "pv_smooth": round(self._pv_smooth, 1),
            "is_sunny": self._is_sunny,
            "pergola_ready": self._pergola_ready,
            "calibrated_today": self.calibrated_today,
            "mode": self._mode,
        }
