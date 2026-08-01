"""Shared scaffolding for coordinator-level tests against a mocked HA.

Not named ``test_*`` so pytest doesn't collect it. Imported from ``conftest.py``
(which defines the fixtures) and from the coordinator test modules for the
plain helpers below. Only safe to import when
pytest-homeassistant-custom-component is installed.
"""

from __future__ import annotations

from homeassistant.core import Event, HomeAssistant, State

COVER = "cover.pergola"
RAIN = "binary_sensor.rain"
LOCK = "sensor.lock_originator"
PRESENCE = "input_boolean.presence"
AZIMUTH = "sensor.sun_azimuth"
ELEVATION = "sensor.sun_elevation"


def entry_data(**overrides) -> dict:
    """A complete config entry; geometry chosen so the loop yields a real target."""
    data = {
        "cover_entity": COVER,
        "sun_azimuth_entity": AZIMUTH,
        "sun_elevation_entity": ELEVATION,
        "rain_entity": RAIN,
        "presence_entity": PRESENCE,
        "priority_lock_entity": LOCK,
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
        "presence_resume_delay": 30,
    }
    data.update(overrides)
    return data


def mock_working_cover(hass: HomeAssistant) -> dict[str, list]:
    """Register cover services that actually update the cover's tilt.

    ``async_mock_service`` only records calls, so the post-command verify
    always fails — fine for testing refusals, useless when a test needs a
    close to *succeed*. Returns the recorded calls per service name.
    """
    calls: dict[str, list] = {
        "close_cover_tilt": [],
        "open_cover_tilt": [],
        "set_cover_tilt_position": [],
    }

    def _handler(name: str, position):
        async def _handle(call):
            calls[name].append(call)
            pos = (
                call.data.get("tilt_position") if position is None else position
            )
            hass.states.async_set(
                COVER,
                "closed" if pos == 0 else "open",
                {"current_tilt_position": pos},
            )
        return _handle

    hass.services.async_register(
        "cover", "close_cover_tilt", _handler("close_cover_tilt", 0)
    )
    hass.services.async_register(
        "cover", "open_cover_tilt", _handler("open_cover_tilt", 100)
    )
    hass.services.async_register(
        "cover",
        "set_cover_tilt_position",
        _handler("set_cover_tilt_position", None),
    )
    return calls


def state_event(entity_id: str, *, old: str | None, new: str | None) -> Event:
    """Minimal stand-in for a state_changed Event.

    The listeners only read ``data['old_state']`` / ``data['new_state']``.
    """
    return Event(
        "state_changed",
        {
            "entity_id": entity_id,
            "old_state": State(entity_id, old) if old is not None else None,
            "new_state": State(entity_id, new) if new is not None else None,
        },
    )
