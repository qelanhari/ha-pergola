"""Shared test fixtures for Pergola Bioclimatique tests."""

import pytest


@pytest.fixture
def default_config() -> dict:
    """Return a default config entry data dict."""
    return {
        "cover_entity": "cover.pergola",
        "sun_azimuth_entity": "sensor.sun_solar_azimuth",
        "sun_elevation_entity": "sensor.sun_solar_elevation",
        "pv_power_entity": "sensor.pv_power",
        "humidity_entity": "sensor.humidity",
        "priority_lock_entity": "sensor.lock_originator",
        "priority_lock_timer_entity": "sensor.lock_timer",
        "face_azimuth": 130,
        "max_opening_angle": 135,
        "calibration_offset": -10,
        "summer_safety_margin": 10,
        "update_interval": 5,
        "step_size": 5,
        "deadband": 2,
        "cloudy_target": 60,
        "min_useful_percent": 9,
        "humidity_max": 80,
        "min_elevation": 20,
        "pv_max_watts": 3000,
        "pv_sunny_ratio": 0.30,
        "pv_smooth_alpha": 0.4,
        "hysteresis_duration": 900,
    }
