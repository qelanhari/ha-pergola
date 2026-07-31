"""Coordinator-level tests for the rain hold and the safety-lock gates.

The lock path had zero test coverage until v1.21.0, which is how the Somfy
`priority_lock_entity` came to sit in the control loop as a hard, independent
blocker — able to wedge the pergola on a stale `rain` value that the
controller is slow to clear. These tests pin the authority split:

    rain sensor  -> decides whether commands may be sent at all
    somfy lock   -> temperature/security close; `rain` is ignored; any
                    origin excuses a command the controller refused

Run with the .venv-test interpreter (see ``requirements_test.txt``); the whole
module is skipped when pytest-homeassistant-custom-component is absent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import Event, HomeAssistant, State

from custom_components.pergola_bioclimatique.const import DOMAIN, MODE_SUMMER
from custom_components.pergola_bioclimatique.coordinator import PergolaCoordinator

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

COVER = "cover.pergola"
RAIN = "binary_sensor.rain"
LOCK = "sensor.lock_originator"
AZIMUTH = "sensor.sun_azimuth"
ELEVATION = "sensor.sun_elevation"


@pytest.fixture(autouse=True)
def no_sleeping():
    """Skip the 30 s / 45 s post-command verification waits."""
    with patch(
        "custom_components.pergola_bioclimatique.coordinator.asyncio.sleep",
        new=AsyncMock(),
    ):
        yield


def _entry_data(**overrides) -> dict:
    data = {
        "cover_entity": COVER,
        "sun_azimuth_entity": AZIMUTH,
        "sun_elevation_entity": ELEVATION,
        "rain_entity": RAIN,
        "priority_lock_entity": LOCK,
        # Geometry / operation: enough for the loop to produce a real target.
        "face_azimuth": 180,
        "max_opening_angle": 135,
        "calibration_offset": 0,
        "blade_pitch_ratio": 0.92,
        "flip_profile_threshold": 84,
        "summer_blade_offset": 0,
        "phase_a_intercept": 40,
        "sun_az_min": 90,
        "sun_az_max": 270,
        "update_interval": 5,
        "step_size": 5,
        "deadband": 2,
        "cloudy_target": 60,
        "min_useful_percent": 9,
        "humidity_max": 80,
        "min_elevation": 20,
        "rain_clear_delay": 10,
    }
    data.update(overrides)
    return data


@pytest.fixture
async def make_coordinator(hass: HomeAssistant):
    """Factory for a coordinator past first-run and morning calibration.

    Tears every coordinator down afterwards — `async_setup` registers a
    midnight-reset time listener that otherwise lingers past the test.
    """
    created: list[PergolaCoordinator] = []

    async def _factory(
        *, tilt: int = 20, rain: str = "off", lock: str = "unknown", **config
    ) -> PergolaCoordinator:
        hass.states.async_set(COVER, "open", {"current_tilt_position": tilt})
        hass.states.async_set(AZIMUTH, "180")
        hass.states.async_set(ELEVATION, "50")
        hass.states.async_set(RAIN, rain)
        hass.states.async_set(LOCK, lock)
        await hass.async_block_till_done()

        entry = MockConfigEntry(
            domain=DOMAIN, data=_entry_data(**config), options={}, title="Pergola"
        )
        entry.add_to_hass(hass)
        coordinator = PergolaCoordinator(hass, entry)
        await coordinator.async_setup()
        created.append(coordinator)

        # Get past the guards that aren't under test here.
        coordinator._first_run = False
        coordinator._pergola_ready = True
        coordinator._descent_calibrated = True
        coordinator._mode = MODE_SUMMER
        coordinator._is_sunny = True
        return coordinator

    yield _factory

    for coordinator in created:
        await coordinator.async_teardown()


def _state_event(entity_id: str, *, old: str | None, new: str | None) -> Event:
    """Minimal stand-in for a state_changed Event.

    The listeners only read ``data['old_state']`` / ``data['new_state']``, so
    a shim keeps these tests readable.
    """
    return Event(
        "state_changed",
        {
            "entity_id": entity_id,
            "old_state": State(entity_id, old) if old is not None else None,
            "new_state": State(entity_id, new) if new is not None else None,
        },
    )


class TestRainHoldGate:
    async def test_wet_sensor_issues_no_commands(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """The whole point of the feature: silence while it's raining."""
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")
        close = async_mock_service(hass, "cover", "close_cover_tilt")
        open_ = async_mock_service(hass, "cover", "open_cover_tilt")

        coordinator = await make_coordinator(rain="on")
        await coordinator._async_update_data()

        assert coordinator.rain_hold is True
        assert not set_tilt and not close and not open_

    async def test_dry_sensor_moves(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Control: with no rain and no lock, the loop does command a move."""
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator()
        await coordinator._async_update_data()

        assert coordinator.rain_hold is False
        assert len(set_tilt) == 1


class TestSomfyLockGate:
    async def test_somfy_rain_lock_does_not_block(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """The v1.21.0 regression test.

        The controller reports `rain` long after the rain sensor has dried —
        up to ~16 min was observed on real hardware, and it can stick. It
        must not stop the loop, or a stuck value wedges the pergola.
        """
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(lock="rain")
        await coordinator._async_update_data()

        assert coordinator.lock_origin == "rain"
        assert len(set_tilt) == 1, "a stale rain lock must not block movement"

    @pytest.mark.parametrize("origin", ["temperature", "security"])
    async def test_closing_lock_closes(
        self, hass: HomeAssistant, make_coordinator, origin: str
    ) -> None:
        """Hardware-protection alarms the rain sensor can't see."""
        close = async_mock_service(hass, "cover", "close_cover_tilt")
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(tilt=50, lock=origin)
        await coordinator._async_update_data()

        assert len(close) == 1
        assert not set_tilt, "no solar target while a safety lock is active"

    @pytest.mark.parametrize("origin", ["temperature", "security"])
    async def test_closing_lock_is_idempotent(
        self, hass: HomeAssistant, make_coordinator, origin: str
    ) -> None:
        """Already closed → don't re-issue close on every 5-minute tick."""
        close = async_mock_service(hass, "cover", "close_cover_tilt")

        coordinator = await make_coordinator(tilt=0, lock=origin)
        await coordinator._async_update_data()

        assert not close

    async def test_unknown_origin_is_not_a_lock(
        self, make_coordinator
    ) -> None:
        """`unknown` is what an idle Somfy io box reports."""
        coordinator = await make_coordinator(lock="unknown")
        assert coordinator.lock_origin == ""


class TestRefusedVersusFailedMove:
    """A command the controller refused is not a mechanical fault.

    The cover state never changes in these tests, so the post-command verify
    always fails; only the lock's presence differs.
    """

    async def test_refusal_does_not_light_movement_problem(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        async_mock_service(hass, "cover", "set_cover_tilt_position")
        coordinator = await make_coordinator(tilt=20, lock="rain")

        ok = await coordinator._async_move_and_verify(COVER, 65)

        assert ok is False
        assert coordinator.movement_ok is True
        assert coordinator._consecutive_failures == 0

    async def test_refusal_leaves_last_known_position_alone(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """We never reached 65% — don't claim we did, or the morning
        drift-skip would compare against a position that never existed."""
        async_mock_service(hass, "cover", "set_cover_tilt_position")
        coordinator = await make_coordinator(tilt=20, lock="rain")
        coordinator._last_known_position = 20.0

        await coordinator._async_move_and_verify(COVER, 65)

        assert coordinator._last_known_position == 20.0

    async def test_genuine_failure_still_counts(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """No lock reported → the pergola really is stuck. Alert."""
        async_mock_service(hass, "cover", "set_cover_tilt_position")
        coordinator = await make_coordinator(tilt=20, lock="unknown")

        ok = await coordinator._async_move_and_verify(COVER, 65)

        assert ok is False
        assert coordinator.movement_ok is False
        assert coordinator._consecutive_failures == 1

    async def test_refused_close_does_not_count(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        async_mock_service(hass, "cover", "close_cover_tilt")
        coordinator = await make_coordinator(tilt=50, lock="rain")

        ok = await coordinator._async_close_and_verify(COVER)

        assert ok is False
        assert coordinator.movement_ok is True


class TestStartupTransitions:
    """Entity-added events must not kick the control loop.

    v1.20.0's rain listener refreshed on any event, including the one fired
    when the entity is first added at startup. That ran the full loop about a
    second after HA booted — before the cover integration could accept a
    command and before the lock sensor had reported — and commanded a move
    that the controller then refused.
    """

    @pytest.mark.parametrize("listener", ["_on_rain_change", "_on_lock_change"])
    async def test_entity_added_does_not_refresh(
        self, hass: HomeAssistant, make_coordinator, listener: str
    ) -> None:
        coordinator = await make_coordinator()
        entity = RAIN if listener == "_on_rain_change" else LOCK

        with patch.object(
            coordinator, "async_request_refresh", new=AsyncMock()
        ) as refresh:
            # old_state None is the signature of an entity being added.
            getattr(coordinator, listener)(
                _state_event(entity, old=None, new="off")
            )
            await hass.async_block_till_done()

        refresh.assert_not_called()

    async def test_lock_transition_refreshes(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """A real lock appearing must be acted on without waiting a tick."""
        coordinator = await make_coordinator()

        with patch.object(
            coordinator, "async_request_refresh", new=AsyncMock()
        ) as refresh:
            coordinator._on_lock_change(
                _state_event(LOCK, old="unknown", new="temperature")
            )
            await hass.async_block_till_done()

        refresh.assert_called_once()

    async def test_rain_to_dry_does_not_refresh_while_held(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Rain stopping doesn't resume tracking — the clear delay runs first.

        Refreshing here would be pointless work: the loop would just hit the
        rain gate and return.
        """
        coordinator = await make_coordinator()

        with patch.object(
            coordinator, "async_request_refresh", new=AsyncMock()
        ) as refresh:
            coordinator._on_rain_change(_state_event(RAIN, old="on", new="off"))
            await hass.async_block_till_done()

        assert coordinator.rain_hold is True
        refresh.assert_not_called()

    async def test_rain_to_dry_refreshes_when_delay_is_zero(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """With a self-debouncing source, resume as soon as it reads dry."""
        coordinator = await make_coordinator(rain_clear_delay=0)

        with patch.object(
            coordinator, "async_request_refresh", new=AsyncMock()
        ) as refresh:
            coordinator._on_rain_change(_state_event(RAIN, old="on", new="off"))
            await hass.async_block_till_done()

        assert coordinator.rain_hold is False
        refresh.assert_called_once()

    async def test_rain_onset_stamps_last_on(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """off→on records when it started, so the clear delay has a base."""
        coordinator = await make_coordinator()
        assert coordinator._rain_last_on is None

        coordinator._on_rain_change(_state_event(RAIN, old="off", new="on"))
        await hass.async_block_till_done()

        assert coordinator._rain_last_on is not None
