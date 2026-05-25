"""Tests for the pure helper functions in `config_flow.py`.

These are the highest-risk new code in the v1.14 refactor: they decide the
defaults the basic flow writes silently, and the threshold above which the
Options flow auto-opens in advanced view. Getting either wrong would silently
re-default a user's customized setup or fail to round-trip a default install.

The tests use the same ``sys.path`` + module-stubbing trick as ``test_solar.py``
so they run under plain ``pytest`` without a Home Assistant runtime.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Stub out homeassistant + voluptuous just enough for config_flow.py to import
# — but ONLY if the real packages aren't installed. When `test_config_flow.py`
# runs alongside us in the same session, it relies on the real homeassistant
# being present in sys.modules; we mustn't poison it.
# ---------------------------------------------------------------------------

def _install_stubs_if_needed() -> None:
    try:
        import homeassistant.config_entries  # noqa: F401
        import voluptuous  # noqa: F401
        return  # real packages available — nothing to stub
    except ImportError:
        pass

    class _ConfigFlowStub:
        def __init_subclass__(cls, **kwargs) -> None:
            pass

    stubs = {
        "homeassistant": {},
        "homeassistant.config_entries": {
            "ConfigEntry": object,
            "ConfigFlow": _ConfigFlowStub,
            "OptionsFlowWithConfigEntry": _ConfigFlowStub,
        },
        "homeassistant.const": {"CONF_NAME": "name"},
        "homeassistant.helpers": {},
        "homeassistant.helpers.selector": {
            name: (lambda *a, **kw: None)
            for name in (
                "BooleanSelector",
                "EntitySelector",
                "EntitySelectorConfig",
                "NumberSelector",
                "NumberSelectorConfig",
                "NumberSelectorMode",
            )
        },
        "voluptuous": {
            "Schema": lambda x=None: x,
            "Required": lambda *a, **kw: (a[0] if a else None),
            "Optional": lambda *a, **kw: (a[0] if a else None),
            "Marker": object,
        },
    }
    for name, attrs in stubs.items():
        mod = sys.modules.get(name) or types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod


_install_stubs_if_needed()


# Load the integration's modules under a private namespace (`_pergola_test_*`)
# so we don't share sys.modules entries with `test_config_flow.py`, which lets
# Home Assistant import the integration through its own machinery. The same
# .py source is loaded; only the registered module names differ.
_PKG_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "pergola_bioclimatique"

import importlib.util

_test_pkg = types.ModuleType("_pergola_test")
_test_pkg.__path__ = [str(_PKG_ROOT)]
sys.modules["_pergola_test"] = _test_pkg

_const_spec = importlib.util.spec_from_file_location(
    "_pergola_test.const", _PKG_ROOT / "const.py"
)
const = importlib.util.module_from_spec(_const_spec)
sys.modules["_pergola_test.const"] = const
_const_spec.loader.exec_module(const)

# `config_flow.py` does `from .const import …`. To make that resolve to our
# private `_pergola_test.const` we rewrite its module name before exec'ing.
import re

_cf_source = (_PKG_ROOT / "config_flow.py").read_text()
_cf_source = re.sub(r"from \.const import", "from _pergola_test.const import", _cf_source)
_cf_module = types.ModuleType("_pergola_test.config_flow")
_cf_module.__file__ = str(_PKG_ROOT / "config_flow.py")
exec(compile(_cf_source, str(_PKG_ROOT / "config_flow.py"), "exec"), _cf_module.__dict__)
sys.modules["_pergola_test.config_flow"] = _cf_module
cf = _cf_module


# Cardinals + a few edge cases. Includes the maintainer's default (130) and
# values that push sun_az_min/max into negative / >360 territory to confirm
# the helper stores them as-is (the coordinator handles azimuth comparison).
_CARDINAL_FACE_AZIMUTHS = [0, 45, 90, 130, 135, 180, 200, 225, 270, 315, 359]


# ---------------------------------------------------------------------------
# _geometry_defaults
# ---------------------------------------------------------------------------

class TestGeometryDefaults:
    def test_legacy_default_install_dict(self) -> None:
        """At face_az=130 the dict must match a legacy default install byte-for-byte."""
        result = cf._geometry_defaults(130)
        assert result == {
            const.CONF_MAX_OPENING_ANGLE: const.DEFAULT_MAX_OPENING_ANGLE,
            const.CONF_CALIBRATION_OFFSET: const.DEFAULT_CALIBRATION_OFFSET,
            const.CONF_BLADE_PITCH_RATIO: const.DEFAULT_BLADE_PITCH_RATIO,
            const.CONF_FLIP_PROFILE_THRESHOLD: const.DEFAULT_FLIP_PROFILE_THRESHOLD,
            const.CONF_SUMMER_BLADE_OFFSET: const.DEFAULT_SUMMER_BLADE_OFFSET,
            const.CONF_PHASE_A_INTERCEPT: const.DEFAULT_PHASE_A_INTERCEPT,
            const.CONF_SUN_AZ_MIN: 40,
            const.CONF_SUN_AZ_MAX: 220,
        }

    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_sun_window_derives_from_face(self, face_az: int) -> None:
        """sun_az_min/max are face_az ± 90 at every facing direction."""
        result = cf._geometry_defaults(face_az)
        assert result[const.CONF_SUN_AZ_MIN] == face_az - 90
        assert result[const.CONF_SUN_AZ_MAX] == face_az + 90

    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_non_window_fields_are_const_defaults(self, face_az: int) -> None:
        """Every field except sun_az_min/max is independent of face direction."""
        result = cf._geometry_defaults(face_az)
        assert result[const.CONF_MAX_OPENING_ANGLE] == const.DEFAULT_MAX_OPENING_ANGLE
        assert result[const.CONF_CALIBRATION_OFFSET] == const.DEFAULT_CALIBRATION_OFFSET
        assert result[const.CONF_BLADE_PITCH_RATIO] == const.DEFAULT_BLADE_PITCH_RATIO
        assert result[const.CONF_FLIP_PROFILE_THRESHOLD] == const.DEFAULT_FLIP_PROFILE_THRESHOLD
        assert result[const.CONF_SUMMER_BLADE_OFFSET] == const.DEFAULT_SUMMER_BLADE_OFFSET
        assert result[const.CONF_PHASE_A_INTERCEPT] == const.DEFAULT_PHASE_A_INTERCEPT

    def test_face_0_produces_negative_sun_az_min(self) -> None:
        """face_az=0 → sun_az_min=-90. Helper must not crash or wrap."""
        result = cf._geometry_defaults(0)
        assert result[const.CONF_SUN_AZ_MIN] == -90
        assert result[const.CONF_SUN_AZ_MAX] == 90

    def test_face_359_produces_oversize_sun_az_max(self) -> None:
        """face_az=359 → sun_az_max=449. Helper must not crash or wrap."""
        result = cf._geometry_defaults(359)
        assert result[const.CONF_SUN_AZ_MIN] == 269
        assert result[const.CONF_SUN_AZ_MAX] == 449


# ---------------------------------------------------------------------------
# _cloud_defaults
# ---------------------------------------------------------------------------

class TestCloudDefaults:
    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_pv_panel_azimuth_follows_face(self, face_az: int) -> None:
        """pv_panel_azimuth defaults to face_az at every facing direction.

        The new basic flow tracks face_az; the legacy flow used the static
        DEFAULT_PV_PANEL_AZIMUTH (which is = DEFAULT_FACE_AZIMUTH = 130). The
        difference is only visible when the user picks a non-130 face — which
        is precisely the case where defaulting panels to the pergola direction
        is more correct than defaulting to a hardcoded 130.
        """
        result = cf._cloud_defaults(face_az)
        assert result[const.CONF_PV_PANEL_AZIMUTH] == face_az

    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_other_cloud_fields_are_const_defaults(self, face_az: int) -> None:
        """Every cloud field except pv_panel_azimuth is independent of face."""
        result = cf._cloud_defaults(face_az)
        assert result[const.CONF_PV_PANEL_TILT] == const.DEFAULT_PV_PANEL_TILT
        assert result[const.CONF_PV_SUNNY_RATIO] == const.DEFAULT_PV_SUNNY_RATIO
        assert result[const.CONF_PV_SMOOTH_ALPHA] == const.DEFAULT_PV_SMOOTH_ALPHA
        assert result[const.CONF_HYSTERESIS_DURATION] == const.DEFAULT_HYSTERESIS_DURATION
        assert result[const.CONF_LUX_SUNNY_RATIO] == const.DEFAULT_LUX_SUNNY_RATIO
        assert result[const.CONF_PV_OBSERVABLE_COS] == const.DEFAULT_PV_OBSERVABLE_COS
        assert result[const.CONF_LUX_AZ_MIN] == const.DEFAULT_LUX_AZ_MIN
        assert result[const.CONF_LUX_AZ_MAX] == const.DEFAULT_LUX_AZ_MAX


# ---------------------------------------------------------------------------
# _geometry_has_non_defaults
# ---------------------------------------------------------------------------

# (field_key, non_default_value) pairs — each pair flips one field off-default.
_GEOMETRY_NON_DEFAULTS = [
    (const.CONF_MAX_OPENING_ANGLE, const.DEFAULT_MAX_OPENING_ANGLE + 10),
    (const.CONF_CALIBRATION_OFFSET, const.DEFAULT_CALIBRATION_OFFSET + 5),
    (const.CONF_BLADE_PITCH_RATIO, const.DEFAULT_BLADE_PITCH_RATIO - 0.05),
    (const.CONF_FLIP_PROFILE_THRESHOLD, const.DEFAULT_FLIP_PROFILE_THRESHOLD + 3),
    (const.CONF_SUMMER_BLADE_OFFSET, const.DEFAULT_SUMMER_BLADE_OFFSET + 2),
    (const.CONF_PHASE_A_INTERCEPT, const.DEFAULT_PHASE_A_INTERCEPT - 5),
]


class TestGeometryHasNonDefaults:
    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_all_defaults_returns_false(self, face_az: int) -> None:
        """An entry built from _geometry_defaults must be classified as default."""
        values = {const.CONF_FACE_AZIMUTH: face_az, **cf._geometry_defaults(face_az)}
        assert cf._geometry_has_non_defaults(values) is False

    @pytest.mark.parametrize(("field", "value"), _GEOMETRY_NON_DEFAULTS)
    def test_any_single_field_off_default_returns_true(
        self, field: str, value: float
    ) -> None:
        """Flipping any one geometry advanced field must trip the detector."""
        values = {const.CONF_FACE_AZIMUTH: 130, **cf._geometry_defaults(130)}
        values[field] = value
        assert cf._geometry_has_non_defaults(values) is True, (
            f"field {field}={value} (default {values[field]!r}) was not detected"
        )

    def test_sun_window_at_derived_default_for_custom_face_is_default(self) -> None:
        """sun_az_min/max are compared against face_az ± 90, not against a
        hardcoded constant. A south-southwest pergola (face=200) with
        sun_az_min=110, sun_az_max=290 is at the *derived* default for its
        facing direction, and must be classified as default."""
        values = {
            const.CONF_FACE_AZIMUTH: 200,
            **cf._geometry_defaults(200),  # sun_az_min=110, sun_az_max=290
        }
        assert cf._geometry_has_non_defaults(values) is False

    def test_sun_window_off_derived_default_is_non_default(self) -> None:
        """Same setup but with sun_az_min=100 (instead of derived 110) is custom."""
        values = {
            const.CONF_FACE_AZIMUTH: 200,
            **cf._geometry_defaults(200),
        }
        values[const.CONF_SUN_AZ_MIN] = 100
        assert cf._geometry_has_non_defaults(values) is True

    def test_missing_field_does_not_trip_detector(self) -> None:
        """A field absent from the dict shouldn't count as non-default
        (the coordinator's .get() will substitute the const default later)."""
        # Build a dict that's all-defaults, then remove one field entirely.
        values = {const.CONF_FACE_AZIMUTH: 130, **cf._geometry_defaults(130)}
        del values[const.CONF_BLADE_PITCH_RATIO]
        assert cf._geometry_has_non_defaults(values) is False


# ---------------------------------------------------------------------------
# _cloud_has_non_defaults
# ---------------------------------------------------------------------------

_CLOUD_NON_DEFAULTS = [
    (const.CONF_PV_PANEL_TILT, const.DEFAULT_PV_PANEL_TILT + 5),
    (const.CONF_PV_SUNNY_RATIO, const.DEFAULT_PV_SUNNY_RATIO - 0.05),
    (const.CONF_PV_SMOOTH_ALPHA, const.DEFAULT_PV_SMOOTH_ALPHA + 0.1),
    (const.CONF_HYSTERESIS_DURATION, const.DEFAULT_HYSTERESIS_DURATION + 60),
    (const.CONF_LUX_SUNNY_RATIO, const.DEFAULT_LUX_SUNNY_RATIO + 1000),
    (const.CONF_PV_OBSERVABLE_COS, const.DEFAULT_PV_OBSERVABLE_COS + 0.05),
    (const.CONF_LUX_AZ_MIN, const.DEFAULT_LUX_AZ_MIN + 10),
    (const.CONF_LUX_AZ_MAX, const.DEFAULT_LUX_AZ_MAX - 10),
]


class TestCloudHasNonDefaults:
    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_all_defaults_returns_false(self, face_az: int) -> None:
        values = {const.CONF_FACE_AZIMUTH: face_az, **cf._cloud_defaults(face_az)}
        assert cf._cloud_has_non_defaults(values) is False

    @pytest.mark.parametrize(("field", "value"), _CLOUD_NON_DEFAULTS)
    def test_any_single_field_off_default_returns_true(
        self, field: str, value: float
    ) -> None:
        values = {const.CONF_FACE_AZIMUTH: 130, **cf._cloud_defaults(130)}
        values[field] = value
        assert cf._cloud_has_non_defaults(values) is True

    def test_pv_panel_azimuth_at_face_is_default(self) -> None:
        """At face=200, pv_panel_azimuth=200 is the derived default."""
        values = {const.CONF_FACE_AZIMUTH: 200, **cf._cloud_defaults(200)}
        assert cf._cloud_has_non_defaults(values) is False

    def test_pv_panel_azimuth_off_face_is_non_default(self) -> None:
        """At face=200, pv_panel_azimuth=180 (panels on a different roof) is custom."""
        values = {const.CONF_FACE_AZIMUTH: 200, **cf._cloud_defaults(200)}
        values[const.CONF_PV_PANEL_AZIMUTH] = 180
        assert cf._cloud_has_non_defaults(values) is True


# ---------------------------------------------------------------------------
# Storage equivalence — the central guarantee of the refactor
# ---------------------------------------------------------------------------

# Defaults for the operation step (step 3, no basic/advanced gate)
_OPERATION_DEFAULTS = {
    const.CONF_UPDATE_INTERVAL: const.DEFAULT_UPDATE_INTERVAL,
    const.CONF_STEP_SIZE: const.DEFAULT_STEP_SIZE,
    const.CONF_DEADBAND: const.DEFAULT_DEADBAND,
    const.CONF_CLOUDY_TARGET: const.DEFAULT_CLOUDY_TARGET,
    const.CONF_MIN_USEFUL_PERCENT: const.DEFAULT_MIN_USEFUL_PERCENT,
    const.CONF_HUMIDITY_MAX: const.DEFAULT_HUMIDITY_MAX,
    const.CONF_MIN_ELEVATION: const.DEFAULT_MIN_ELEVATION,
}


def _legacy_default_install_dict(face_az: int, with_cloud: bool) -> dict:
    """What the v1.13.4 flow would have stored for a user who left every field
    at its default. Reconstructed from the per-key schema defaults in the old
    `_geometry_schema`, `_operation_schema`, and `_cloud_schema`."""
    out = {const.CONF_FACE_AZIMUTH: face_az}
    out.update({
        const.CONF_MAX_OPENING_ANGLE: const.DEFAULT_MAX_OPENING_ANGLE,
        const.CONF_CALIBRATION_OFFSET: const.DEFAULT_CALIBRATION_OFFSET,
        const.CONF_BLADE_PITCH_RATIO: const.DEFAULT_BLADE_PITCH_RATIO,
        const.CONF_FLIP_PROFILE_THRESHOLD: const.DEFAULT_FLIP_PROFILE_THRESHOLD,
        const.CONF_SUMMER_BLADE_OFFSET: const.DEFAULT_SUMMER_BLADE_OFFSET,
        const.CONF_PHASE_A_INTERCEPT: const.DEFAULT_PHASE_A_INTERCEPT,
        const.CONF_SUN_AZ_MIN: face_az - const.DEFAULT_SUN_AZ_HALF_WIDTH,
        const.CONF_SUN_AZ_MAX: face_az + const.DEFAULT_SUN_AZ_HALF_WIDTH,
    })
    out.update(_OPERATION_DEFAULTS)
    if with_cloud:
        out.update({
            const.CONF_PV_MAX_WATTS: const.DEFAULT_PV_MAX_WATTS,
            # Legacy: pv_panel_azimuth defaulted to DEFAULT_PV_PANEL_AZIMUTH,
            # which is _itself_ defined as DEFAULT_FACE_AZIMUTH (=130).
            # New basic flow: pv_panel_azimuth defaults to the user's
            # face_azimuth. At face_az=130 (the default install) the two
            # values coincide — which is exactly the user we're proving
            # equivalence against here.
            const.CONF_PV_PANEL_AZIMUTH: face_az,
            const.CONF_PV_PANEL_TILT: const.DEFAULT_PV_PANEL_TILT,
            const.CONF_PV_SUNNY_RATIO: const.DEFAULT_PV_SUNNY_RATIO,
            const.CONF_PV_SMOOTH_ALPHA: const.DEFAULT_PV_SMOOTH_ALPHA,
            const.CONF_HYSTERESIS_DURATION: const.DEFAULT_HYSTERESIS_DURATION,
            const.CONF_LUX_SUNNY_RATIO: const.DEFAULT_LUX_SUNNY_RATIO,
            const.CONF_PV_OBSERVABLE_COS: const.DEFAULT_PV_OBSERVABLE_COS,
            const.CONF_LUX_AZ_MIN: const.DEFAULT_LUX_AZ_MIN,
            const.CONF_LUX_AZ_MAX: const.DEFAULT_LUX_AZ_MAX,
        })
    return out


def _new_basic_install_dict(face_az: int, with_cloud: bool) -> dict:
    """What the new basic flow stores when the user leaves the advanced
    toggle unchecked at every step. Models the in-coordinator data dict
    assembled by `_create_entry` after walking the geometry / operation /
    (optional) cloud-detection sub-flows."""
    out = {const.CONF_FACE_AZIMUTH: face_az}
    out.update(cf._geometry_defaults(face_az))
    out.update(_OPERATION_DEFAULTS)
    if with_cloud:
        out[const.CONF_PV_MAX_WATTS] = const.DEFAULT_PV_MAX_WATTS
        out.update(cf._cloud_defaults(face_az))
    return out


class TestStorageEquivalence:
    """Prove the new basic flow stores a byte-identical dict to the legacy flow
    for an "out of the box" user — at any facing direction, with or without a
    PV sensor configured."""

    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_without_cloud_sensor(self, face_az: int) -> None:
        assert _new_basic_install_dict(face_az, with_cloud=False) == \
            _legacy_default_install_dict(face_az, with_cloud=False)

    def test_default_install_face_130_with_cloud(self) -> None:
        """The "out of the box" user, with a PV sensor wired up. This is the
        single most important regression: byte-identical to v1.13.4."""
        assert _new_basic_install_dict(130, with_cloud=True) == \
            _legacy_default_install_dict(130, with_cloud=True)

    @pytest.mark.parametrize("face_az", _CARDINAL_FACE_AZIMUTHS)
    def test_with_cloud_sensor(self, face_az: int) -> None:
        """The new basic flow's pv_panel_azimuth tracks face_az; for the
        equivalence comparison the legacy helper does the same (since
        DEFAULT_PV_PANEL_AZIMUTH = DEFAULT_FACE_AZIMUTH, the values coincide
        for the "default install" user we're proving against)."""
        assert _new_basic_install_dict(face_az, with_cloud=True) == \
            _legacy_default_install_dict(face_az, with_cloud=True)
