"""Coordinator-level tests for summer presence parking.

An empty house doesn't stop the pergola on the spot — that would mean an
extra close/open pair every time someone steps out. Instead it keeps
tracking until the algorithm's *next natural close through 0%* (the morning
calibration, or the descent the summer phase A→B flip forces), parks there,
and stays shut across days until presence has been back for the resume
delay. Winter mode is untouched.

Run with the .venv-test interpreter; skipped when the HA test plugin is absent.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from coordinator_harness import PRESENCE, mock_working_cover, state_event

from custom_components.pergola_bioclimatique.const import MODE_WINTER

from pytest_homeassistant_custom_component.common import async_mock_service


class TestAwayDoesNotActImmediately:
    """Leaving must not itself move anything."""

    async def test_away_keeps_tracking_until_a_close(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")
        close = async_mock_service(hass, "cover", "close_cover_tilt")

        # tilt 20 -> target is above it, so this cycle opens: no descent, no latch.
        coordinator = await make_coordinator(tilt=20, presence="off")
        await coordinator._async_update_data()

        assert coordinator.presence_away is True
        assert coordinator.presence_parked is False
        assert len(set_tilt) == 1, "still tracking before the first close"
        assert not close

    async def test_away_alone_does_not_park(
        self, make_coordinator
    ) -> None:
        coordinator = await make_coordinator(presence="off")
        assert coordinator.presence_parked is False


class TestLatch:
    """The next close-through-0% is where an empty house parks."""

    async def test_descent_parks_instead_of_reopening(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """The summer flip forces a descent; away, we stop at 0% and stay.

        Sun overhead and past the flip threshold (84°) puts us in phase B,
        whose target is ~15% — so the loop wants a big descent from 90%. The
        descent recalibration closes through 0%: that's the parking moment.
        """
        coordinator = await make_coordinator(
            tilt=90, presence="off", elevation="88", azimuth="180"
        )
        coordinator._descent_calibrated = False
        calls = mock_working_cover(hass)

        await coordinator._async_update_data()

        assert coordinator.presence_parked is True
        assert len(calls["close_cover_tilt"]) == 1, "the descent close happened"
        assert not calls["set_cover_tilt_position"], (
            "must NOT reopen to the computed target"
        )
        assert coordinator.final_target == 0.0

    async def test_parked_survives_a_restart(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Persisted, so the pergola stays shut the next day too."""
        coordinator = await make_coordinator(presence="off")
        coordinator._presence_parked = True
        await coordinator._save_state()

        second = await make_coordinator(presence="off")
        assert second._presence_parked is True

    async def test_parked_holds_target_at_zero(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        close = async_mock_service(hass, "cover", "close_cover_tilt")
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(tilt=0, presence="off")
        coordinator._presence_parked = True
        await coordinator._async_update_data()

        assert coordinator.final_target == 0.0
        # Already at 0% — the deadband means no command at all.
        assert not close and not set_tilt


class TestResume:
    async def test_brief_return_does_not_resume(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """30 min of continuous presence is required — a flap isn't enough."""
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(tilt=0, presence="on")
        coordinator._presence_parked = True
        await coordinator._async_update_data()

        assert coordinator._presence_parked is True, "still within the delay"
        assert not set_tilt

    async def test_resumes_after_the_delay(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(tilt=0, presence="on")
        coordinator._presence_parked = True
        # Presence has been back for longer than presence_resume_delay.
        coordinator._presence_on_since = dt_util.utcnow() - timedelta(minutes=31)

        await coordinator._async_update_data()

        assert coordinator._presence_parked is False
        assert len(set_tilt) == 1, "tracking resumes"

    async def test_zero_delay_resumes_at_once(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        async_mock_service(hass, "cover", "set_cover_tilt_position")
        coordinator = await make_coordinator(
            tilt=0, presence="on", presence_resume_delay=0
        )
        coordinator._presence_parked = True

        await coordinator._async_update_data()

        assert coordinator._presence_parked is False

    async def test_leaving_again_restarts_the_clock(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """A return that doesn't last must not bank credit toward the delay."""
        coordinator = await make_coordinator(presence="on")
        coordinator._presence_parked = True
        coordinator._note_presence()
        assert coordinator._presence_on_since is not None

        hass.states.async_set(PRESENCE, "off")
        await hass.async_block_till_done()
        coordinator._note_presence()

        assert coordinator._presence_on_since is None


class TestScopeAndSafety:
    async def test_winter_is_unaffected(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Presence parking is a summer feature only."""
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(
            tilt=20, presence="off", mode=MODE_WINTER
        )
        coordinator._presence_parked = True

        assert coordinator.presence_parked is False
        await coordinator._async_update_data()
        assert len(set_tilt) == 1, "winter keeps tracking regardless"

    @pytest.mark.parametrize("state", ["unknown", "unavailable", "home", "on"])
    async def test_only_a_positive_away_counts(
        self, make_coordinator, state: str
    ) -> None:
        """A broken or missing tracker must never park the pergola."""
        coordinator = await make_coordinator(presence=state)
        assert coordinator.presence_away is False

    @pytest.mark.parametrize("state", ["off", "not_home"])
    async def test_both_away_vocabularies(
        self, make_coordinator, state: str
    ) -> None:
        """binary_sensor/input_boolean say `off`; person/device_tracker `not_home`."""
        coordinator = await make_coordinator(presence=state)
        assert coordinator.presence_away is True

    async def test_no_presence_entity_is_inert(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        set_tilt = async_mock_service(hass, "cover", "set_cover_tilt_position")

        coordinator = await make_coordinator(tilt=20, presence_entity=None)
        await coordinator._async_update_data()

        assert coordinator.presence_away is False
        assert coordinator.presence_parked is False
        assert len(set_tilt) == 1


class TestCalibrationInteraction:
    async def test_parked_skips_calibration(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Once parked, don't calibrate — `ready` stays off, nothing moves."""
        close = async_mock_service(hass, "cover", "close_cover_tilt")

        coordinator = await make_coordinator(
            tilt=0, presence="off", ready=False
        )
        coordinator._presence_parked = True

        await coordinator._async_calibrate()

        assert not close
        assert coordinator._pergola_ready is False
        assert coordinator._calibration_deferred is True

    async def test_calibration_before_parking_latches(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Not yet parked: calibration runs, and its close is what parks us.

        This is what reconciles "calibration is a close phase" with "skip
        calibration while away" — the first one after leaving does the
        parking, and every later one is skipped by the test above.
        """
        coordinator = await make_coordinator(
            tilt=50, presence="off", ready=False
        )
        # A cover that really closes, so close-and-verify succeeds.
        mock_working_cover(hass)
        # No last-known position → drift-skip can't apply, so calibration
        # performs a real close. (The drift-skip branch never moves, so it
        # correctly does not latch — see test_drift_skip_does_not_latch.)
        coordinator._last_known_position = None

        await coordinator._async_calibrate()

        assert coordinator._presence_parked is True
        assert coordinator._pergola_ready is True


    async def test_drift_skip_does_not_latch(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Skipping the close means the blades aren't at 0% — so don't claim
        to be parked there. Only a close that actually ran can latch."""
        calls = mock_working_cover(hass)

        coordinator = await make_coordinator(
            tilt=50, presence="off", ready=False
        )
        coordinator._last_known_position = 50.0  # matches tilt → drift-skip

        await coordinator._async_calibrate()

        assert not calls["close_cover_tilt"], "drift-skip issues no command"
        assert coordinator._presence_parked is False


class TestPresenceListener:
    async def test_entity_added_does_not_refresh(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Same startup guard as the rain and lock listeners."""
        coordinator = await make_coordinator()

        with patch.object(
            coordinator, "async_request_refresh", new=AsyncMock()
        ) as refresh:
            coordinator._on_presence_change(
                state_event(PRESENCE, old=None, new="on")
            )
            await hass.async_block_till_done()

        refresh.assert_not_called()

    async def test_arrival_refreshes(
        self, hass: HomeAssistant, make_coordinator
    ) -> None:
        """Starts the resume clock on the next cycle, not up to 5 min later."""
        coordinator = await make_coordinator()

        with patch.object(
            coordinator, "async_request_refresh", new=AsyncMock()
        ) as refresh:
            coordinator._on_presence_change(
                state_event(PRESENCE, old="off", new="on")
            )
            await hass.async_block_till_done()

        refresh.assert_called_once()
