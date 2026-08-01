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

from homeassistant.core import HomeAssistant

from coordinator_harness import COVER, LOCK, RAIN, state_event

from pytest_homeassistant_custom_component.common import async_mock_service


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
                state_event(entity, old=None, new="off")
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
                state_event(LOCK, old="unknown", new="temperature")
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
            coordinator._on_rain_change(state_event(RAIN, old="on", new="off"))
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
            coordinator._on_rain_change(state_event(RAIN, old="on", new="off"))
            await hass.async_block_till_done()

        assert coordinator.rain_hold is False
        refresh.assert_called_once()

    async def test_rain_onset_stamps_last_on(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """off→on records when it started, so the clear delay has a base."""
        coordinator = await make_coordinator()
        assert coordinator._rain_last_on is None

        coordinator._on_rain_change(state_event(RAIN, old="off", new="on"))
        await hass.async_block_till_done()

        assert coordinator._rain_last_on is not None
