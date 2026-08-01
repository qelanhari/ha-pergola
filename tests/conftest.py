"""Shared test fixtures for Pergola Bioclimatique tests.

Three fixtures cover the realistic configuration matrix:

- ``default_config`` — every ``CONF_*`` at its ``DEFAULT_*``, used to assert that
  the basic flow stores a byte-identical entry to a legacy default install.
- ``minimal_config`` — required entities only (no PV / lux / humidity / lock),
  so the skip-cloud-step branch can be exercised.
- ``customized_config`` — face_azimuth=200 with several geometry and cloud
  fields off-default, used to drive the Options auto-advanced behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Make sibling helper modules (coordinator_harness) importable without turning
# tests/ into a package — same convention test_solar.py uses for the component.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _ha_plugin_available() -> bool:
    try:
        import pytest_homeassistant_custom_component  # noqa: F401
    except ImportError:
        return False
    return True


# The coordinator fixtures below need a real Home Assistant runtime. Defining
# them here (rather than importing them into each test module) keeps pytest's
# auto-discovery happy without every module re-importing fixture names.
if _ha_plugin_available():

    @pytest.fixture(autouse=True)
    def no_sleeping():
        """Skip the 30 s / 45 s post-command verification waits."""
        with patch(
            "custom_components.pergola_bioclimatique.coordinator.asyncio.sleep",
            new=AsyncMock(),
        ):
            yield

    @pytest.fixture
    async def make_coordinator(hass):
        """Factory for a coordinator past first-run and morning calibration.

        Tears every coordinator down afterwards — ``async_setup`` registers a
        midnight-reset time listener, and a refresh request arms a debouncer;
        both otherwise linger past the test.
        """
        from coordinator_harness import (
            AZIMUTH,
            COVER,
            ELEVATION,
            LOCK,
            PRESENCE,
            RAIN,
            entry_data,
        )
        from custom_components.pergola_bioclimatique.const import MODE_SUMMER
        from custom_components.pergola_bioclimatique.coordinator import (
            PergolaCoordinator,
        )
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        created: list = []

        async def _factory(
            *,
            tilt: int = 20,
            rain: str = "off",
            lock: str = "unknown",
            presence: str = "on",
            elevation: str = "50",
            azimuth: str = "180",
            mode: str = MODE_SUMMER,
            ready: bool = True,
            **config,
        ):
            hass.states.async_set(COVER, "open", {"current_tilt_position": tilt})
            hass.states.async_set(AZIMUTH, azimuth)
            hass.states.async_set(ELEVATION, elevation)
            hass.states.async_set(RAIN, rain)
            hass.states.async_set(LOCK, lock)
            hass.states.async_set(PRESENCE, presence)
            await hass.async_block_till_done()

            entry = MockConfigEntry(
                domain="pergola_bioclimatique",
                data=entry_data(**config),
                options={},
                title="Pergola",
            )
            entry.add_to_hass(hass)
            coordinator = PergolaCoordinator(hass, entry)
            await coordinator.async_setup()
            created.append(coordinator)

            # Get past the guards that aren't under test.
            coordinator._first_run = False
            coordinator._pergola_ready = ready
            coordinator._descent_calibrated = True
            coordinator._mode = mode
            coordinator._is_sunny = True
            return coordinator

        yield _factory

        for coordinator in created:
            await coordinator.async_teardown()
            await coordinator.async_shutdown()


# Centralised defaults — kept in sync with ``const.py``. If a test fails after
# a schema change, update this dict here in one place.
_DEFAULT_CONFIG: dict = {
    # Step 1 — entities
    "cover_entity": "cover.pergola",
    "sun_azimuth_entity": "sensor.sun_solar_azimuth",
    "sun_elevation_entity": "sensor.sun_solar_elevation",
    "pv_power_entity": "sensor.pv_power",
    "light_sensor_entity": "sensor.outdoor_lux",
    "humidity_entity": "sensor.humidity",
    "rain_entity": "binary_sensor.rain",
    "presence_entity": "input_boolean.presence",
    "priority_lock_entity": "sensor.lock_originator",
    # Step 2 — geometry (face_azimuth=130 drives sun_az_min/max defaults)
    "face_azimuth": 130,
    "max_opening_angle": 135,
    "calibration_offset": -10,
    "blade_pitch_ratio": 0.92,
    "flip_profile_threshold": 80,
    "summer_blade_offset": 0,
    "phase_a_intercept": 40,
    "sun_az_min": 40,   # 130 − 90
    "sun_az_max": 220,  # 130 + 90
    # Step 3 — operation
    "update_interval": 5,
    "step_size": 5,
    "deadband": 2,
    "cloudy_target": 60,
    "min_useful_percent": 9,
    "humidity_max": 80,
    "min_elevation": 20,
    "rain_clear_delay": 10,
    "presence_resume_delay": 30,
    # Step 4 — cloud detection (pv_panel_azimuth defaults to face_azimuth)
    "pv_max_watts": 3000,
    "pv_panel_azimuth": 130,
    "pv_panel_tilt": 30,
    "pv_sunny_ratio": 0.50,
    "pv_smooth_alpha": 0.4,
    "hysteresis_duration": 900,
    "lux_sunny_ratio": 25000,
    "pv_observable_cos": 0.4,
    "lux_az_min": 120,
    "lux_az_max": 260,
}


@pytest.fixture
def default_config() -> dict:
    """Every ``CONF_*`` at its ``DEFAULT_*``. The dict is what a legacy default
    install would have stored (and what the new basic flow now stores too)."""
    return dict(_DEFAULT_CONFIG)


@pytest.fixture
def minimal_config() -> dict:
    """Required entities only — no PV, lux, humidity, or safety lock.

    Used to verify the install flow skips the cloud-detection step and the
    coordinator handles missing optional inputs gracefully.
    """
    cfg = dict(_DEFAULT_CONFIG)
    for k in (
        "pv_power_entity",
        "light_sensor_entity",
        "humidity_entity",
        "rain_entity",
        "presence_entity",
        "priority_lock_entity",
        "priority_lock_timer_entity",
        # Cloud-detection fields aren't stored when no cloud sensor is set
        "pv_max_watts",
        "pv_panel_azimuth",
        "pv_panel_tilt",
        "pv_sunny_ratio",
        "pv_smooth_alpha",
        "hysteresis_duration",
        "lux_sunny_ratio",
        "pv_observable_cos",
        "lux_az_min",
        "lux_az_max",
    ):
        cfg.pop(k, None)
    return cfg


@pytest.fixture
def customized_config() -> dict:
    """A southwest-facing pergola with non-default geometry and cloud values.

    Drives the Options flow's auto-advanced behavior: any non-default in
    `_GEOMETRY_ADVANCED_FIELDS` or `_CLOUD_ADVANCED_FIELDS` should open the
    matching advanced step instead of the basic gate.
    """
    cfg = dict(_DEFAULT_CONFIG)
    cfg.update({
        "face_azimuth": 200,
        # Sun window correctly derives to face ± 90 for the new azimuth
        "sun_az_min": 110,
        "sun_az_max": 290,
        # Non-default geometry tweaks
        "calibration_offset": -5,
        "blade_pitch_ratio": 0.88,
        "summer_blade_offset": 3,
        # Non-default cloud tweaks (panel on a different roof slope)
        "pv_panel_azimuth": 180,
        "pv_panel_tilt": 25,
        "pv_sunny_ratio": 0.45,
    })
    return cfg
