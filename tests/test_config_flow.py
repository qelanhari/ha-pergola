"""End-to-end tests for the install + Options config flows.

Walks the flow with a mocked Home Assistant instance (provided by
``pytest-homeassistant-custom-component``). The hass fixture and
``enable_custom_integrations`` come from that plugin's conftest.

Run with the .venv-test interpreter (see ``requirements_test.txt``):

    .venv-test/bin/pytest tests/test_config_flow.py -v

These tests are skipped when the plugin isn't installed — the helper-level
suite in ``test_config_flow_helpers.py`` still exercises the same logic from
a different angle, so no coverage is lost on developer machines without the
heavier dependency.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Skip the whole module if pytest-homeassistant-custom-component isn't installed.
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pergola_bioclimatique.config_flow import (
    SUN_AZIMUTH_ENTITY,
    SUN_ELEVATION_ENTITY,
)
from custom_components.pergola_bioclimatique.const import (
    CONF_BLADE_PITCH_RATIO,
    CONF_CALIBRATION_OFFSET,
    CONF_CLOUDY_TARGET,
    CONF_COVER_ENTITY,
    CONF_DEADBAND,
    CONF_FACE_AZIMUTH,
    CONF_FLIP_PROFILE_THRESHOLD,
    CONF_HUMIDITY_MAX,
    CONF_HYSTERESIS_DURATION,
    CONF_LUX_AZ_MAX,
    CONF_LUX_AZ_MIN,
    CONF_LUX_SUNNY_RATIO,
    CONF_MAX_OPENING_ANGLE,
    CONF_MIN_ELEVATION,
    CONF_MIN_USEFUL_PERCENT,
    CONF_PHASE_A_INTERCEPT,
    CONF_PV_MAX_WATTS,
    CONF_PV_OBSERVABLE_COS,
    CONF_PV_PANEL_AZIMUTH,
    CONF_PV_PANEL_TILT,
    CONF_PV_POWER_ENTITY,
    CONF_PV_SMOOTH_ALPHA,
    CONF_PV_SUNNY_RATIO,
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
    DEFAULT_FLIP_PROFILE_THRESHOLD,
    DEFAULT_HUMIDITY_MAX,
    DEFAULT_HYSTERESIS_DURATION,
    DEFAULT_LUX_AZ_MAX,
    DEFAULT_LUX_AZ_MIN,
    DEFAULT_LUX_SUNNY_RATIO,
    DEFAULT_MAX_OPENING_ANGLE,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_MIN_USEFUL_PERCENT,
    DEFAULT_PHASE_A_INTERCEPT,
    DEFAULT_PV_MAX_WATTS,
    DEFAULT_PV_OBSERVABLE_COS,
    DEFAULT_PV_PANEL_TILT,
    DEFAULT_PV_SMOOTH_ALPHA,
    DEFAULT_PV_SUNNY_RATIO,
    DEFAULT_STEP_SIZE,
    DEFAULT_SUMMER_BLADE_OFFSET,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-applied: let HA discover `custom_components/pergola_bioclimatique`."""
    yield


# Allow lingering timers/tasks from the dependent Sun integration. HA loads
# `sun` automatically (it's in our manifest's `dependencies`) and schedules
# periodic recompute timers; we're testing the config flow, not Sun's lifecycle.
@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    return True


@pytest.fixture(autouse=True)
def expected_lingering_tasks() -> bool:
    return True


@pytest.fixture(autouse=True)
def stub_setup_entry():
    """Patch out ``async_setup_entry`` so flow tests don't spin up the real
    coordinator (which schedules a periodic timer that lingers past teardown).
    We're testing the config flow's output, not the integration's runtime.
    """
    with patch(
        "custom_components.pergola_bioclimatique.async_setup_entry",
        return_value=True,
    ), patch(
        "custom_components.pergola_bioclimatique.async_unload_entry",
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_sun_states(hass: HomeAssistant):
    """Register the Sun integration's well-known sensors in hass.states."""
    hass.states.async_set(SUN_AZIMUTH_ENTITY, "130.0")
    hass.states.async_set(SUN_ELEVATION_ENTITY, "45.0")
    yield


# Entity payload submitted at step 1. Includes the cover and sun entities
# (validated against hass.states); other entity slots are blank by default,
# tests that need them register/pass them explicitly.
def _step1_payload(*, pv: str | None = None, light: str | None = None) -> dict:
    data = {
        CONF_NAME: "Pergola",
        CONF_COVER_ENTITY: "cover.pergola",
        CONF_SUN_AZIMUTH_ENTITY: SUN_AZIMUTH_ENTITY,
        CONF_SUN_ELEVATION_ENTITY: SUN_ELEVATION_ENTITY,
    }
    if pv is not None:
        data[CONF_PV_POWER_ENTITY] = pv
    if light is not None:
        data["light_sensor_entity"] = light
    return data


def _step3_default_operation() -> dict:
    """Operation step accepts defaults — no basic/advanced split here."""
    return {
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_STEP_SIZE: DEFAULT_STEP_SIZE,
        CONF_DEADBAND: DEFAULT_DEADBAND,
        CONF_CLOUDY_TARGET: DEFAULT_CLOUDY_TARGET,
        CONF_MIN_USEFUL_PERCENT: DEFAULT_MIN_USEFUL_PERCENT,
        CONF_HUMIDITY_MAX: DEFAULT_HUMIDITY_MAX,
        CONF_MIN_ELEVATION: DEFAULT_MIN_ELEVATION,
    }


def _expected_default_data(face_az: int, *, with_cloud: bool) -> dict:
    """The dict the new basic flow stores when the user leaves everything at
    default. Mirror of `tests/test_config_flow_helpers.py::_new_basic_install_dict`."""
    data = {
        CONF_COVER_ENTITY: "cover.pergola",
        CONF_SUN_AZIMUTH_ENTITY: SUN_AZIMUTH_ENTITY,
        CONF_SUN_ELEVATION_ENTITY: SUN_ELEVATION_ENTITY,
        CONF_FACE_AZIMUTH: face_az,
        CONF_MAX_OPENING_ANGLE: DEFAULT_MAX_OPENING_ANGLE,
        CONF_CALIBRATION_OFFSET: DEFAULT_CALIBRATION_OFFSET,
        CONF_BLADE_PITCH_RATIO: DEFAULT_BLADE_PITCH_RATIO,
        CONF_FLIP_PROFILE_THRESHOLD: DEFAULT_FLIP_PROFILE_THRESHOLD,
        CONF_SUMMER_BLADE_OFFSET: DEFAULT_SUMMER_BLADE_OFFSET,
        CONF_PHASE_A_INTERCEPT: DEFAULT_PHASE_A_INTERCEPT,
        CONF_SUN_AZ_MIN: face_az - 90,
        CONF_SUN_AZ_MAX: face_az + 90,
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_STEP_SIZE: DEFAULT_STEP_SIZE,
        CONF_DEADBAND: DEFAULT_DEADBAND,
        CONF_CLOUDY_TARGET: DEFAULT_CLOUDY_TARGET,
        CONF_MIN_USEFUL_PERCENT: DEFAULT_MIN_USEFUL_PERCENT,
        CONF_HUMIDITY_MAX: DEFAULT_HUMIDITY_MAX,
        CONF_MIN_ELEVATION: DEFAULT_MIN_ELEVATION,
    }
    if with_cloud:
        data[CONF_PV_POWER_ENTITY] = "sensor.pv_power"
        data[CONF_PV_MAX_WATTS] = DEFAULT_PV_MAX_WATTS
        data[CONF_PV_PANEL_AZIMUTH] = face_az
        data[CONF_PV_PANEL_TILT] = DEFAULT_PV_PANEL_TILT
        data[CONF_PV_SUNNY_RATIO] = DEFAULT_PV_SUNNY_RATIO
        data[CONF_PV_SMOOTH_ALPHA] = DEFAULT_PV_SMOOTH_ALPHA
        data[CONF_HYSTERESIS_DURATION] = DEFAULT_HYSTERESIS_DURATION
        data[CONF_LUX_SUNNY_RATIO] = DEFAULT_LUX_SUNNY_RATIO
        data[CONF_PV_OBSERVABLE_COS] = DEFAULT_PV_OBSERVABLE_COS
        data[CONF_LUX_AZ_MIN] = DEFAULT_LUX_AZ_MIN
        data[CONF_LUX_AZ_MAX] = DEFAULT_LUX_AZ_MAX
    return data


# ---------------------------------------------------------------------------
# Install flow
# ---------------------------------------------------------------------------

class TestInstallFlow:
    """Walk the install wizard and assert what lands in `entry.data`.

    Each test starts a fresh flow, submits each step in turn, and verifies the
    transitions and final stored data. The "basic-only" case is the most
    important: it must produce a dict byte-identical to a legacy default install.
    """

    async def test_basic_only_no_cloud(
        self, hass: HomeAssistant, mock_sun_states
    ) -> None:
        """The 'out of the box' user: cover + sun + leave every default → no
        cloud step (no PV entity) → byte-identical to legacy default install."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step1_payload()
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "geometry"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_FACE_AZIMUTH: DEFAULT_FACE_AZIMUTH, "advanced": False},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "operation"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step3_default_operation()
        )
        # No cloud sensor configured → flow finishes here
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Pergola"
        assert result["data"] == _expected_default_data(
            DEFAULT_FACE_AZIMUTH, with_cloud=False
        )

    async def test_basic_only_with_pv_uses_basic_cloud(
        self, hass: HomeAssistant, mock_sun_states
    ) -> None:
        """Same default user but with a PV sensor → cloud step appears →
        basic cloud (just pv_max_watts) → fills cloud defaults silently."""
        hass.states.async_set("sensor.pv_power", "2400")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step1_payload(pv="sensor.pv_power")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_FACE_AZIMUTH: DEFAULT_FACE_AZIMUTH, "advanced": False},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step3_default_operation()
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cloud_detection"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PV_MAX_WATTS: DEFAULT_PV_MAX_WATTS, "advanced": False},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == _expected_default_data(
            DEFAULT_FACE_AZIMUTH, with_cloud=True
        )

    async def test_advanced_geometry_preserves_user_values(
        self, hass: HomeAssistant, mock_sun_states
    ) -> None:
        """Tick advanced on geometry, customize blade_pitch_ratio and
        sun_az_min/max → those custom values land in entry.data."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step1_payload()
        )
        # Basic geometry — request advanced
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_FACE_AZIMUTH: 200, "advanced": True},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "geometry_advanced"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_FACE_AZIMUTH: 200,
                CONF_MAX_OPENING_ANGLE: DEFAULT_MAX_OPENING_ANGLE,
                CONF_CALIBRATION_OFFSET: -5,
                CONF_BLADE_PITCH_RATIO: 0.88,
                CONF_FLIP_PROFILE_THRESHOLD: 78,
                CONF_SUMMER_BLADE_OFFSET: 3,
                CONF_PHASE_A_INTERCEPT: 45,
                CONF_SUN_AZ_MIN: 100,
                CONF_SUN_AZ_MAX: 295,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "operation"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step3_default_operation()
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Confirm the user's customizations made it through
        assert result["data"][CONF_FACE_AZIMUTH] == 200
        assert result["data"][CONF_CALIBRATION_OFFSET] == -5
        assert result["data"][CONF_BLADE_PITCH_RATIO] == 0.88
        assert result["data"][CONF_FLIP_PROFILE_THRESHOLD] == 78
        assert result["data"][CONF_SUMMER_BLADE_OFFSET] == 3
        assert result["data"][CONF_PHASE_A_INTERCEPT] == 45
        assert result["data"][CONF_SUN_AZ_MIN] == 100
        assert result["data"][CONF_SUN_AZ_MAX] == 295

    async def test_advanced_cloud_preserves_user_values(
        self, hass: HomeAssistant, mock_sun_states
    ) -> None:
        """Tick advanced on cloud, customize a few fields → preserved in entry.data."""
        hass.states.async_set("sensor.pv_power", "2400")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step1_payload(pv="sensor.pv_power")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_FACE_AZIMUTH: DEFAULT_FACE_AZIMUTH, "advanced": False},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _step3_default_operation()
        )
        # Tick advanced on cloud step
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PV_MAX_WATTS: DEFAULT_PV_MAX_WATTS, "advanced": True},
        )
        assert result["step_id"] == "cloud_detection_advanced"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PV_MAX_WATTS: 5000,
                CONF_PV_PANEL_AZIMUTH: 180,  # PV panels on a different roof slope
                CONF_PV_PANEL_TILT: 25,
                CONF_PV_SUNNY_RATIO: 0.45,
                CONF_PV_SMOOTH_ALPHA: DEFAULT_PV_SMOOTH_ALPHA,
                CONF_HYSTERESIS_DURATION: DEFAULT_HYSTERESIS_DURATION,
                CONF_LUX_SUNNY_RATIO: DEFAULT_LUX_SUNNY_RATIO,
                CONF_PV_OBSERVABLE_COS: DEFAULT_PV_OBSERVABLE_COS,
                CONF_LUX_AZ_MIN: DEFAULT_LUX_AZ_MIN,
                CONF_LUX_AZ_MAX: DEFAULT_LUX_AZ_MAX,
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PV_MAX_WATTS] == 5000
        assert result["data"][CONF_PV_PANEL_AZIMUTH] == 180
        assert result["data"][CONF_PV_PANEL_TILT] == 25
        assert result["data"][CONF_PV_SUNNY_RATIO] == 0.45

    async def test_entity_not_found_error(
        self, hass: HomeAssistant, mock_sun_states
    ) -> None:
        """Submitting a sun azimuth that isn't in hass.states keeps the user
        on step 1 with an `entity_not_found` error. The valid elevation is
        registered via `mock_sun_states` so only the bad entity flags."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Pergola",
                CONF_COVER_ENTITY: "cover.pergola",
                CONF_SUN_AZIMUTH_ENTITY: "sensor.does_not_exist",
                CONF_SUN_ELEVATION_ENTITY: SUN_ELEVATION_ENTITY,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {CONF_SUN_AZIMUTH_ENTITY: "entity_not_found"}


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------

def _full_default_entry_data(*, with_cloud: bool = False) -> dict:
    """Same as _expected_default_data but starts from a sensible name."""
    return _expected_default_data(DEFAULT_FACE_AZIMUTH, with_cloud=with_cloud)


class TestOptionsFlow:
    """Verify the Options flow opens in the right view based on stored data.

    The key UX guarantee: a user who customized something sees their values
    in the advanced view, not silently re-defaulted to the basic.
    """

    async def test_default_entry_opens_basic_geometry(
        self, hass: HomeAssistant
    ) -> None:
        """An entry with all defaults → Options opens in `geometry_basic`."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=_full_default_entry_data(),
            options={},
            title="Pergola",
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "geometry_basic"

    async def test_customized_geometry_opens_advanced(
        self, hass: HomeAssistant
    ) -> None:
        """An entry with a non-default blade_pitch_ratio → Options opens
        directly in `geometry_advanced`, with the customized value visible."""
        data = _full_default_entry_data()
        data[CONF_BLADE_PITCH_RATIO] = 0.88  # non-default
        entry = MockConfigEntry(domain=DOMAIN, data=data, options={}, title="Pergola")
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "geometry_advanced"

    async def test_customized_cloud_opens_advanced(
        self, hass: HomeAssistant
    ) -> None:
        """An entry with a non-default pv_observable_cos → after the geometry
        and operation steps, Options opens directly in `cloud_detection_advanced`."""
        data = _full_default_entry_data(with_cloud=True)
        data[CONF_PV_OBSERVABLE_COS] = 0.55  # non-default
        entry = MockConfigEntry(domain=DOMAIN, data=data, options={}, title="Pergola")
        entry.add_to_hass(hass)

        # Walk past geometry_basic and operation to get to the cloud branch.
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "geometry_basic"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FACE_AZIMUTH: DEFAULT_FACE_AZIMUTH, "advanced": False},
        )
        assert result["step_id"] == "operation"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], _step3_default_operation()
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cloud_detection_advanced"

    async def test_no_cloud_sensor_skips_cloud_step(
        self, hass: HomeAssistant
    ) -> None:
        """An entry without PV/lux saves after operation without ever showing
        a cloud step (basic or advanced)."""
        data = _full_default_entry_data(with_cloud=False)
        entry = MockConfigEntry(domain=DOMAIN, data=data, options={}, title="Pergola")
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "geometry_basic"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_FACE_AZIMUTH: DEFAULT_FACE_AZIMUTH, "advanced": False},
        )
        assert result["step_id"] == "operation"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], _step3_default_operation()
        )
        # No PV/light entity in entry.data → save immediately
        assert result["type"] == FlowResultType.CREATE_ENTRY
