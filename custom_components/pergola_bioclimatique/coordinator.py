"""DataUpdateCoordinator for Pergola Bioclimatique."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import solar
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
    DEFAULT_STEP_SIZE,
    DEFAULT_SUMMER_BLADE_OFFSET,
    DEFAULT_SUN_AZ_HALF_WIDTH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    entry_value,
    LOCK_ORIGINS,
    LOCK_RAIN,
    LOCK_SECURITY,
    LOCK_TEMPERATURE,
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
                minutes=self._opt(
                    entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                )
            ),
        )
        self.config_entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub_listeners: list[Any] = []

        # Internal state (replaces all helper entities)
        self._mode: str = MODE_WINTER
        self._pv_smooth: float = 0.0
        self._lux_smooth: float = 0.0
        self._pv_smooth_stale: bool = True
        self._is_sunny: bool = False
        self._sunny_restore_fresh: bool = False
        self._sunny_changed_at: datetime = datetime.min
        self._last_calibration: date | None = None
        self._pergola_ready: bool = False
        self._descent_calibrated: bool = False
        self._calibrating: bool = False
        # Set when rain or a safety lock turned calibration away; the next
        # unblocked cycle retries it. Not persisted — a restart re-arms the
        # elevation listener anyway.
        self._calibration_deferred: bool = False
        self._watchdog_running: bool = False
        # Last moment the rain sensor was observed on (UTC). Persisted, so a
        # restart mid-shower resumes the remaining clear delay instead of
        # holding for a fresh full window. None = rain never seen.
        self._rain_last_on: datetime | None = None
        self._consecutive_failures: int = 0
        self._first_run: bool = True
        self._mode_just_changed: bool = False
        self._sunny_just_changed: bool = False
        # Last position the integration successfully commanded; survives
        # restarts via Store. Used to skip the morning calibration cycle
        # when the cover hasn't drifted overnight.
        self._last_known_position: float | None = None

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

    @property
    def movement_ok(self) -> bool:
        return self._consecutive_failures == 0

    @property
    def rain_hold(self) -> bool:
        """True while the rain sensor holds all movement.

        The pergola control unit gets the rain signal directly and closes
        itself, so the integration's only job is to stop issuing commands
        (which the unit would refuse anyway) until it's dry again.

        Pure read — the ``_rain_last_on`` timestamp it consumes is stamped
        by ``_note_rain_state`` and ``_on_rain_change``.
        """
        entity_id = self._entity(CONF_RAIN_ENTITY)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        delay = self._cfg(CONF_RAIN_CLEAR_DELAY, DEFAULT_RAIN_CLEAR_DELAY)
        age: float | None = None
        if self._rain_last_on is not None:
            age = (dt_util.utcnow() - self._rain_last_on).total_seconds()
        # unknown/unavailable reads as "not raining" — the control unit is
        # the real protection, so fail open rather than freezing forever.
        return solar.rain_hold_active(
            state.state == STATE_ON, age, float(delay)
        )

    def _note_rain_state(self) -> bool:
        """Stamp ``_rain_last_on`` while the sensor reads on, return the hold.

        Called from the control loop so a continuously-wet sensor keeps the
        timestamp current; without this the delay would be measured from
        the *start* of a long shower and release the moment it ended.
        """
        entity_id = self._entity(CONF_RAIN_ENTITY)
        if entity_id:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == STATE_ON:
                self._rain_last_on = dt_util.utcnow()
        return self.rain_hold

    # --- Config helpers ---

    _opt = staticmethod(entry_value)

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

        # Rain hold: react immediately instead of waiting for the next tick
        rain_entity = self._entity(CONF_RAIN_ENTITY)
        if rain_entity:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, rain_entity, self._on_rain_change
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
            self._lux_smooth = data.get("lux_smooth", 0.0)
            # Persisted pv/lux are stale across long gaps (overnight); the
            # first morning cycle reseeds them from the live sensor.
            self._pv_smooth_stale = True
            self._is_sunny = data.get("is_sunny", False)
            # A same-day save from the last hour (entry reload, quick HA
            # restart) means the restored is_sunny is still valid — don't
            # let the stale-reseed cycle wipe it. Crucial when the reload
            # lands in a sensor blind-spot: with neither PV nor lux
            # observable, a wiped is_sunny would stay False (held) for
            # the rest of the day.
            self._sunny_restore_fresh = solar.is_recent_save(
                data.get("saved_at"), datetime.now(), 3600
            )
            self._mode = data.get("mode", MODE_WINTER)
            last_cal = data.get("last_calibration")
            if last_cal:
                try:
                    self._last_calibration = date.fromisoformat(last_cal)
                except ValueError:
                    self._last_calibration = None
            self._pergola_ready = data.get("pergola_ready", False)
            self._descent_calibrated = data.get("descent_calibrated", False)
            self._consecutive_failures = data.get("consecutive_failures", 0)
            self._last_known_position = data.get("last_known_position")
            rain_last_on = data.get("rain_last_on")
            if rain_last_on:
                try:
                    parsed = datetime.fromisoformat(rain_last_on)
                except (ValueError, TypeError):
                    parsed = None
                # Must be tz-aware to subtract from dt_util.utcnow(); drop a
                # naive value rather than raising on every rain_hold read.
                if parsed is not None and parsed.tzinfo is None:
                    parsed = None
                self._rain_last_on = parsed
            # Do NOT restore sunny_changed_at — after restart, the first
            # cloud detection reading should decide immediately without
            # waiting for the hysteresis timer to expire.

    async def _save_state(self) -> None:
        await self._store.async_save({
            "saved_at": datetime.now().isoformat(),
            "pv_smooth": self._pv_smooth,
            "lux_smooth": self._lux_smooth,
            "is_sunny": self._is_sunny,
            "mode": self._mode,
            "last_calibration": (
                self._last_calibration.isoformat() if self._last_calibration else None
            ),
            "pergola_ready": self._pergola_ready,
            "descent_calibrated": self._descent_calibrated,
            "consecutive_failures": self._consecutive_failures,
            "last_known_position": self._last_known_position,
            "rain_last_on": (
                self._rain_last_on.isoformat() if self._rain_last_on else None
            ),
        })

    # --- Mode control (called from SelectEntity) ---

    async def async_set_mode(self, mode: str) -> None:
        self._mode_just_changed = True
        self._mode = mode
        await self._save_state()
        await self.async_request_refresh()

    # --- Movement with verification ---

    async def _async_move_and_verify(
        self, cover_id: str, target: int, tolerance: int = 5, wait: int = 30,
    ) -> bool:
        """Send move command, wait, verify position reached.

        Uses open/close commands for 100%/0% to preserve motor calibration.
        """
        if target == 0:
            _LOGGER.debug("Command: close cover tilt (0%%)")
            await self.hass.services.async_call(
                "cover", "close_cover_tilt",
                target={"entity_id": cover_id},
            )
        elif target == 100:
            _LOGGER.debug("Command: open cover tilt (100%%)")
            await self.hass.services.async_call(
                "cover", "open_cover_tilt",
                target={"entity_id": cover_id},
            )
        else:
            _LOGGER.debug("Command: set tilt to %d%%", target)
            await self.hass.services.async_call(
                "cover", "set_cover_tilt_position",
                service_data={"tilt_position": target},
                target={"entity_id": cover_id},
            )
        await asyncio.sleep(wait)
        actual = self._get_cover_tilt()
        ok = abs(actual - target) <= tolerance
        if ok:
            self._consecutive_failures = 0
            self._last_known_position = float(target)
            _LOGGER.debug(
                "Verify OK: target=%d%%, actual=%.0f%%", target, actual
            )
        else:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "Verify FAILED: target=%d%%, actual=%.0f%% (failure #%d)",
                target, actual, self._consecutive_failures,
            )
        self.async_set_updated_data(self._build_data())
        return ok

    async def _async_close_and_verify(
        self, cover_id: str, wait: int = 45,
    ) -> bool:
        """Send close command, wait, verify position < 5%."""
        _LOGGER.debug("Command: close cover tilt")
        await self.hass.services.async_call(
            "cover", "close_cover_tilt",
            target={"entity_id": cover_id},
        )
        await asyncio.sleep(wait)
        pos = self._get_cover_tilt()
        ok = pos < 5
        if ok:
            self._consecutive_failures = 0
            self._last_known_position = 0.0
            _LOGGER.debug("Close verify OK: position=%.0f%%", pos)
        else:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "Close verify FAILED: position=%.0f%% (failure #%d)",
                pos, self._consecutive_failures,
            )
        self.async_set_updated_data(self._build_data())
        return ok

    # --- Button actions ---

    async def async_force_recalibrate(self) -> None:
        """Force a recalibration, then move to current target."""
        cover_id = self._entity(CONF_COVER_ENTITY)
        if not cover_id:
            return

        _LOGGER.info("Pergola: forced recalibration requested")
        success = await self._async_close_and_verify(cover_id)
        if success:
            self._descent_calibrated = True
            self._last_calibration = date.today()
            self._pergola_ready = True
            _LOGGER.info("Pergola: forced recalibration successful")
            await self._save_state()
            # Recalculate and move to target
            await self.async_request_refresh()
        else:
            _LOGGER.warning("Pergola: forced recalibration failed")

    async def async_force_refresh(self) -> None:
        """Force a target recalculation without calibration."""
        _LOGGER.info("Pergola: forced target recalculation requested")
        await self.async_request_refresh()

    # --- Descent recalibration ---

    async def _async_recalibrate_descent(self, cover_id: str) -> bool:
        """Recalibrate before a descent. Returns True if successful."""
        ok = await self._async_close_and_verify(cover_id)
        if ok:
            self._descent_calibrated = True
        return ok

    # --- Main control loop (called every N minutes by DataUpdateCoordinator) ---

    async def _async_update_data(self) -> dict[str, Any]:
        """Main control loop — replaces the v3 bioclimat automation."""
        if self._first_run:
            self._first_run = False
            _LOGGER.debug("First refresh: read-only, skipping movements")
            return self._build_data()

        if self._mode == MODE_MANUAL:
            _LOGGER.debug("Skip: mode is Manual")
            return self._build_data()

        azim = self._get_float(self._entity(CONF_SUN_AZIMUTH_ENTITY))
        elev = self._get_float(self._entity(CONF_SUN_ELEVATION_ENTITY))
        current_pos = self._get_cover_tilt()

        _LOGGER.debug(
            "Cycle start: mode=%s, azim=%.1f°, elev=%.1f°, current_pos=%.0f%%, "
            "ready=%s, descent_cal=%s, sunny=%s",
            self._mode, azim, elev, current_pos,
            self._pergola_ready, self._descent_calibrated, self._is_sunny,
        )

        min_elev = self._cfg(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION)
        if elev <= min_elev:
            _LOGGER.debug("Skip: elevation %.1f° ≤ min %.1f°", elev, min_elev)
            return self._build_data()

        # Check humidity block
        humidity_entity = self._entity(CONF_HUMIDITY_ENTITY)
        if humidity_entity:
            humidity = self._get_float(humidity_entity)
            humidity_max = self._cfg(CONF_HUMIDITY_MAX, DEFAULT_HUMIDITY_MAX)
            if humidity >= humidity_max:
                _LOGGER.debug(
                    "Skip: humidity %.0f%% ≥ max %.0f%%", humidity, humidity_max
                )
                return self._build_data()

        # Rain hold — issue nothing at all. The control unit already closed
        # the pergola on its own rain signal and would refuse our commands.
        if self._note_rain_state():
            _LOGGER.debug("Skip: rain hold active")
            # Persist the refreshed timestamp: this path returns before the
            # cycle's normal save, so a long shower would otherwise leave
            # `rain_last_on` stuck at the moment it started raining.
            await self._save_state()
            return self._build_data()

        # Check safety lock
        lock_entity = self._entity(CONF_PRIORITY_LOCK_ENTITY)
        if lock_entity:
            lock_origin = self._get_state(lock_entity)
            if lock_origin in LOCK_ORIGINS:
                _LOGGER.debug("Skip: safety lock active (%s)", lock_origin)
                return self._build_data()

        # Nothing blocks us any more — pick up a calibration that rain or a
        # safety lock deferred this morning. Without this the elevation
        # listener would never fire again today and the pergola would stay
        # not-ready until tomorrow.
        if (
            self._calibration_deferred
            and not self._pergola_ready
            and not self._calibrating
        ):
            self._calibration_deferred = False
            _LOGGER.info("Pergola: retrying deferred morning calibration")
            self.hass.async_create_task(self._async_calibrate())
            return self._build_data()

        # Solar geometry
        face_azimuth = self._cfg(CONF_FACE_AZIMUTH, DEFAULT_FACE_AZIMUTH)
        max_angle = self._cfg(CONF_MAX_OPENING_ANGLE, DEFAULT_MAX_OPENING_ANGLE)
        offset = self._cfg(CONF_CALIBRATION_OFFSET, DEFAULT_CALIBRATION_OFFSET)
        step = self._cfg(CONF_STEP_SIZE, DEFAULT_STEP_SIZE)
        cloudy_target = self._cfg(CONF_CLOUDY_TARGET, DEFAULT_CLOUDY_TARGET)
        min_useful = self._cfg(
            CONF_MIN_USEFUL_PERCENT, DEFAULT_MIN_USEFUL_PERCENT
        )

        self._profile_angle = solar.compute_profile_angle(elev, azim, face_azimuth)

        # Cloud detection first — needed to decide whether to reset winter hold
        self._update_cloud_detection(azim, elev)

        # Compute target based on mode
        # Reset hold after mode switch or cloudy→sunny transition so the
        # winter hold doesn't lock in the cloudy_target position.
        reset_hold = self._mode_just_changed or (
            self._sunny_just_changed and self._is_sunny
        )
        hold_pos = 0.0 if reset_hold else current_pos
        if self._mode == MODE_WINTER:
            solar_percent = solar.compute_winter_target(
                self._profile_angle, offset, hold_pos, max_angle, step
            )
        else:
            pitch_ratio = self._cfg(
                CONF_BLADE_PITCH_RATIO, DEFAULT_BLADE_PITCH_RATIO
            )
            flip_threshold = self._cfg(
                CONF_FLIP_PROFILE_THRESHOLD, DEFAULT_FLIP_PROFILE_THRESHOLD
            )
            sun_az_min = self._cfg(
                CONF_SUN_AZ_MIN, face_azimuth - DEFAULT_SUN_AZ_HALF_WIDTH
            )
            sun_az_max = self._cfg(
                CONF_SUN_AZ_MAX, face_azimuth + DEFAULT_SUN_AZ_HALF_WIDTH
            )
            if not solar.azimuth_in_window(azim, sun_az_min, sun_az_max):
                # Sun outside the pergola's exposure window — the building
                # itself is shadowing the protected zone, no direct rays
                # to block. Fall back to diffuse-light position.
                solar_percent = cloudy_target
                summer_branch = "outside-window"
            else:
                summer_offset = self._cfg(
                    CONF_SUMMER_BLADE_OFFSET, DEFAULT_SUMMER_BLADE_OFFSET
                )
                phase_a_intercept = self._cfg(
                    CONF_PHASE_A_INTERCEPT, DEFAULT_PHASE_A_INTERCEPT
                )
                solar_percent = solar.compute_summer_target(
                    self._profile_angle, offset, max_angle, step,
                    pitch_ratio, flip_threshold,
                    summer_offset, phase_a_intercept,
                    cloudy_target,
                )
                summer_branch = (
                    "phase B (cutoff)"
                    if self._profile_angle >= flip_threshold
                    else "phase A (linear)"
                )

        self._solar_target = solar_percent

        if self._mode == MODE_WINTER:
            _LOGGER.debug(
                "Solar: profile_angle=%.1f°, solar_target=%.0f%%, "
                "sunny=%s, cloudy_target=%d%%, min_useful=%d%%",
                self._profile_angle, solar_percent,
                self._is_sunny, int(cloudy_target), int(min_useful),
            )
        else:
            _LOGGER.debug(
                "Solar: profile=%.1f° az=%.1f° window=[%d°,%d°] "
                "branch=%s flip_threshold=%d° → solar_target=%.0f%% "
                "(sunny=%s, cloudy=%d%%, min_useful=%d%%)",
                self._profile_angle, azim,
                int(sun_az_min), int(sun_az_max),
                summer_branch, int(flip_threshold),
                solar_percent, self._is_sunny,
                int(cloudy_target), int(min_useful),
            )

        # Final target decision.
        # Priority: trust the geometry when the sun is actually shining,
        # even if solar_percent is small (blades flat is a legitimate output
        # for an overhead sun). The min_useful standby is only meant for
        # twilight situations where the geometry alone would point too low.
        if self._is_sunny:
            final = solar_percent
            reason = "sunny → follow solar (%.0f%%)" % solar_percent
        elif solar_percent < min_useful:
            final = cloudy_target
            reason = (
                "standby (no sun & solar %.0f%% < min %.0f%%) → cloudy %d%%"
                % (solar_percent, min_useful, int(cloudy_target))
            )
        elif self._mode == MODE_WINTER:
            final = max(cloudy_target, hold_pos)
            reason = "winter cloudy → hold max(cloudy %d%%, pos %d%%)" % (
                int(cloudy_target), int(hold_pos)
            )
        else:
            final = cloudy_target
            reason = "summer cloudy → standby %d%%" % int(cloudy_target)

        final = solar.quantize(final, step)
        self._final_target = final
        self._mode_just_changed = False
        self._sunny_just_changed = False

        _LOGGER.debug(
            "Decision: %s → final_target=%.0f%%", reason, final
        )

        # Persist pv_smooth every cycle so restarts don't load a stale value
        await self._save_state()

        # Movement gating
        deadband = self._cfg(CONF_DEADBAND, DEFAULT_DEADBAND)
        delta = abs(final - current_pos)
        if delta <= deadband:
            _LOGGER.debug(
                "No move: delta %.0f%% ≤ deadband %d%%", delta, deadband
            )
            return self._build_data()

        if not self._pergola_ready:
            _LOGGER.debug("No move: pergola not ready (awaiting calibration)")
            return self._build_data()

        # Descent calibration logic
        cover_id = self._entity(CONF_COVER_ENTITY)
        if not cover_id:
            _LOGGER.debug("No move: no cover entity configured")
            return self._build_data()

        if final > current_pos + step:
            self._descent_calibrated = False
            _LOGGER.debug("Opening: reset descent calibration flag")

        if final < current_pos - step and not self._descent_calibrated:
            _LOGGER.info(
                "Descent %d%% → %d%% requires recalibration",
                int(current_pos), int(final),
            )
            success = await self._async_recalibrate_descent(cover_id)
            if not success:
                _LOGGER.warning(
                    "Descent recalibration failed — movement blocked"
                )
                return self._build_data()
            _LOGGER.info("Descent recalibration OK")

        # Move pergola
        _LOGGER.info(
            "Moving: %d%% → %d%% (%s)", int(current_pos), int(final), reason
        )
        await self._async_move_and_verify(cover_id, int(final))
        return self._build_data()

    def _update_cloud_detection(self, azim: float, elev: float) -> None:
        """Update smoothed sensors and sunny state with observability gates.

        Each sensor (PV, lux) is only counted when the sun is geometrically
        able to reach it. When neither sensor is observable, the prior
        is_sunny is preserved so a brief blind-spot doesn't flip state.
        """
        pv_entity = self._entity(CONF_PV_POWER_ENTITY)
        light_entity = self._entity(CONF_LIGHT_SENSOR_ENTITY)

        if not pv_entity and not light_entity:
            self._is_sunny = True
            return

        alpha = self._cfg(CONF_PV_SMOOTH_ALPHA, DEFAULT_PV_SMOOTH_ALPHA)
        hysteresis = self._cfg(
            CONF_HYSTERESIS_DURATION, DEFAULT_HYSTERESIS_DURATION
        )

        # PV branch ---------------------------------------------------------
        pv_threshold = 0.0
        pv_observable = False
        pv_raw = 0.0
        if pv_entity:
            pv_raw = self._get_float(pv_entity)
            if self._pv_smooth_stale:
                # Persisted value carries over from yesterday's PV. Reseed
                # from the live sensor on the first cycle that has a
                # plausible reading.
                self._pv_smooth = pv_raw
            else:
                self._pv_smooth = solar.smooth_pv(
                    pv_raw, self._pv_smooth, alpha
                )

            pv_max = self._cfg(CONF_PV_MAX_WATTS, DEFAULT_PV_MAX_WATTS)
            ratio = self._cfg(CONF_PV_SUNNY_RATIO, DEFAULT_PV_SUNNY_RATIO)
            panel_azimuth = self._cfg(
                CONF_PV_PANEL_AZIMUTH, DEFAULT_PV_PANEL_AZIMUTH
            )
            panel_tilt = self._cfg(CONF_PV_PANEL_TILT, DEFAULT_PV_PANEL_TILT)
            pv_threshold = solar.compute_pv_threshold(
                elev, azim, panel_azimuth, panel_tilt, pv_max, ratio,
            )
            cos_aoi = solar.panel_cos_aoi(
                elev, azim, panel_azimuth, panel_tilt
            )
            obs_cos = self._cfg(
                CONF_PV_OBSERVABLE_COS, DEFAULT_PV_OBSERVABLE_COS
            )
            pv_observable = cos_aoi > obs_cos
            _LOGGER.debug(
                "Cloud PV: raw=%.0fW, smooth=%.1fW, thr=%.0fW, "
                "cos_aoi=%.2f (>%.2f? %s)",
                pv_raw, self._pv_smooth, pv_threshold,
                cos_aoi, obs_cos, pv_observable,
            )

        # Lux branch --------------------------------------------------------
        lux_threshold = 0.0
        lux_observable = False
        lux_raw = 0.0
        if light_entity:
            lux_raw = self._get_float(light_entity)
            if self._pv_smooth_stale:
                self._lux_smooth = lux_raw
            else:
                self._lux_smooth = solar.smooth_pv(
                    lux_raw, self._lux_smooth, alpha
                )

            lux_ratio = self._cfg(
                CONF_LUX_SUNNY_RATIO, DEFAULT_LUX_SUNNY_RATIO
            )
            lux_threshold = lux_ratio * math.sin(
                math.radians(max(0.0, elev))
            )
            az_min = self._cfg(CONF_LUX_AZ_MIN, DEFAULT_LUX_AZ_MIN)
            az_max = self._cfg(CONF_LUX_AZ_MAX, DEFAULT_LUX_AZ_MAX)
            lux_observable = solar.azimuth_in_window(azim, az_min, az_max)
            _LOGGER.debug(
                "Cloud lux: raw=%.0f, smooth=%.1f, thr=%.0f, "
                "azim=%.1f in [%.0f,%.0f]? %s",
                lux_raw, self._lux_smooth, lux_threshold,
                azim, az_min, az_max, lux_observable,
            )

        # Stale flag is cleared after the first reseeding cycle. Also wipe
        # the carried-over is_sunny so the first decision on a new day is
        # not inherited from yesterday evening — unless the save is fresh
        # (same-day, recent: entry reload / quick restart), in which case
        # the restored is_sunny is still the correct current state.
        if self._pv_smooth_stale and not self._sunny_restore_fresh:
            self._is_sunny = False
            self._sunny_changed_at = datetime.min
        self._pv_smooth_stale = False

        sunny_now = solar.is_sunny(
            self._pv_smooth, pv_threshold, pv_observable,
            self._lux_smooth, lux_threshold, lux_observable,
            self._is_sunny,
        )
        _LOGGER.debug(
            "Cloud decision: %s (pv_obs=%s, lux_obs=%s)",
            "sunny" if sunny_now else "cloudy",
            pv_observable, lux_observable,
        )

        # Hysteresis: only change state if enough time has passed
        elapsed = (datetime.now() - self._sunny_changed_at).total_seconds()
        if elapsed > hysteresis:
            if sunny_now != self._is_sunny:
                _LOGGER.info(
                    "Sun state changed: %s → %s (after %.0fs hysteresis)",
                    "sunny" if self._is_sunny else "cloudy",
                    "sunny" if sunny_now else "cloudy",
                    elapsed,
                )
                self._is_sunny = sunny_now
                self._sunny_just_changed = True
                self._sunny_changed_at = datetime.now()
        elif sunny_now != self._is_sunny:
            _LOGGER.debug(
                "Cloud: would switch to %s but hysteresis locked (%.0fs / %ds)",
                "sunny" if sunny_now else "cloudy",
                elapsed, hysteresis,
            )

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

        threshold = self._cfg(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION)
        if elev > threshold and not self._pergola_ready and not self._calibrating:
            self.hass.async_create_task(self._async_calibrate())

    @callback
    def _on_rain_change(self, event: Event) -> None:
        """Push the rain_hold sensor and resume promptly once it's dry.

        The hold itself can also expire on a timer (``rain_clear_delay``
        minutes after the sensor goes off) with no state change to observe
        — the regular tick picks that up.
        """
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        old_state = event.data.get("old_state")
        # Stamp on the way in AND on the way out: the moment it goes off,
        # "now" is the last instant it was wet, so the clear delay must run
        # from here — not from whenever the shower started.
        if new_state.state == STATE_ON or (
            old_state is not None and old_state.state == STATE_ON
        ):
            self._rain_last_on = dt_util.utcnow()
            self.hass.async_create_task(self._save_state())
        # async_update_listeners, not async_set_updated_data: the latter
        # reschedules the periodic refresh, so a flickering rain contact
        # would keep pushing the control tick further out. The rain_hold
        # sensor reads the property directly and only needs a state write.
        self.async_update_listeners()
        if not self.rain_hold:
            self.hass.async_create_task(self.async_request_refresh())

    async def _async_calibrate(self) -> None:
        """Morning calibration: close fully, verify, unlock.

        Skips the close-and-verify if the current cover position still
        matches `_last_known_position` (the last value the integration
        successfully commanded). In that case no drift could have
        happened overnight, so we mark today as calibrated without
        moving — avoids the useless full-close cycle when the evening
        target equals the morning target.
        """
        if self.rain_hold:
            _LOGGER.info("Pergola: calibration deferred — rain hold active")
            self._calibration_deferred = True
            return

        lock_entity = self._entity(CONF_PRIORITY_LOCK_ENTITY)
        if lock_entity:
            lock_origin = self._get_state(lock_entity)
            if lock_origin in LOCK_ORIGINS:
                _LOGGER.info(
                    "Pergola: calibration deferred — safety lock (%s)",
                    lock_origin,
                )
                self._calibration_deferred = True
                return

        cover_id = self._entity(CONF_COVER_ENTITY)
        if not cover_id:
            return

        self._calibrating = True
        try:
            today = date.today()
            if self._last_calibration != today:
                current_pos = self._get_cover_tilt()
                last_known = self._last_known_position
                deadband = self._cfg(CONF_DEADBAND, DEFAULT_DEADBAND)

                if (
                    last_known is not None
                    and abs(current_pos - last_known) <= deadband
                ):
                    _LOGGER.info(
                        "Pergola: skip morning calibration — position "
                        "%d%% matches last known %d%% (no drift)",
                        int(current_pos), int(last_known),
                    )
                    self._last_calibration = today
                else:
                    _LOGGER.info(
                        "Pergola: starting morning calibration "
                        "(position=%d%%, last known=%s)",
                        int(current_pos),
                        f"{int(last_known)}%" if last_known is not None
                        else "unknown",
                    )
                    success = await self._async_close_and_verify(cover_id)
                    if not success:
                        _LOGGER.warning(
                            "Pergola: morning calibration failed"
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
        self._calibration_deferred = False
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

                if origin in (LOCK_TEMPERATURE, LOCK_SECURITY):
                    await self._async_close_and_verify(cover_id)
                    await asyncio.sleep(75)  # extra wait for safety
                elif origin == LOCK_RAIN:
                    # A rain lock is a hold, not a movement: the control
                    # unit has already closed the pergola and refuses
                    # commands. Re-asserting the current tilt here only
                    # fed _consecutive_failures and falsely lit the
                    # movement_problem sensor.
                    _LOGGER.debug("Rain lock: holding, no command issued")

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
            "movement_ok": self.movement_ok,
            "rain_hold": self.rain_hold,
        }
