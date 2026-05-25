"""Tests for `presets.py` — the pergola model preset registry.

Every shipped preset must have a valid schema, every numeric value must lie
within the same min/max bounds the config-flow's NumberSelector imposes, and
every preset's `values` keys must be real `CONF_*` constants from the geometry
advanced field list. Catches typos and out-of-range values early.

Uses the same `sys.path` + module-isolation pattern as `test_config_flow_helpers.py`
so it runs under plain pytest without a Home Assistant runtime.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


def _install_stubs_if_needed() -> None:
    try:
        import homeassistant.config_entries  # noqa: F401
        import voluptuous  # noqa: F401
        return
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
                "SelectSelector",
                "SelectSelectorConfig",
                "SelectSelectorMode",
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


# Load const, presets, and config_flow under a private namespace so we don't
# clash with the real integration when test_config_flow.py runs in the same
# session under the venv.
_PKG_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "pergola_bioclimatique"

import importlib.util
import re

_test_pkg = types.ModuleType("_pergola_test_presets")
_test_pkg.__path__ = [str(_PKG_ROOT)]
sys.modules["_pergola_test_presets"] = _test_pkg


def _load_module(name: str, source_filename: str, rewrites: dict[str, str] | None = None) -> types.ModuleType:
    source = (_PKG_ROOT / source_filename).read_text()
    if rewrites:
        for old, new in rewrites.items():
            source = source.replace(old, new)
    mod = types.ModuleType(f"_pergola_test_presets.{name}")
    mod.__file__ = str(_PKG_ROOT / source_filename)
    exec(compile(source, str(_PKG_ROOT / source_filename), "exec"), mod.__dict__)
    sys.modules[f"_pergola_test_presets.{name}"] = mod
    return mod


const = _load_module("const", "const.py")
# presets.py does `from .const import …`; rewrite to our private namespace.
presets = _load_module(
    "presets",
    "presets.py",
    rewrites={"from .const import": "from _pergola_test_presets.const import"},
)
# config_flow.py also does relative imports.
config_flow = _load_module(
    "config_flow",
    "config_flow.py",
    rewrites={
        "from .const import": "from _pergola_test_presets.const import",
        "from .presets import": "from _pergola_test_presets.presets import",
    },
)


# ---------------------------------------------------------------------------
# Bounds derived from the NumberSelector configs in config_flow.py — these
# must stay in sync with the form validation.
# ---------------------------------------------------------------------------

_GEOMETRY_BOUNDS: dict[str, tuple[float, float]] = {
    const.CONF_MAX_OPENING_ANGLE: (90, 180),
    const.CONF_CALIBRATION_OFFSET: (-30, 30),
    const.CONF_BLADE_PITCH_RATIO: (0.5, 1.2),
    const.CONF_FLIP_PROFILE_THRESHOLD: (60, 90),
    const.CONF_SUMMER_BLADE_OFFSET: (-30, 30),
    const.CONF_PHASE_A_INTERCEPT: (0, 80),
    const.CONF_SUN_AZ_MIN: (0, 360),
    const.CONF_SUN_AZ_MAX: (0, 360),
}


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestPresetSchema:
    """Every entry in PRESETS has the documented structure."""

    def test_required_keys(self) -> None:
        for model_id, preset in presets.PRESETS.items():
            assert isinstance(model_id, str) and model_id, f"empty model id"
            assert set(preset).issuperset(
                {"display_name", "brand", "values", "source", "source_url", "notes"}
            ), f"{model_id} missing required keys: have {set(preset)}"

    def test_types(self) -> None:
        for model_id, preset in presets.PRESETS.items():
            assert isinstance(preset["display_name"], str) and preset["display_name"], model_id
            assert isinstance(preset["brand"], str), model_id
            assert isinstance(preset["values"], dict), model_id
            assert preset["source"] in ("verified", "community"), model_id
            assert isinstance(preset["source_url"], str), model_id
            assert isinstance(preset["notes"], str), model_id


class TestCustomPreset:
    """The `custom` preset is the fallback identity."""

    def test_custom_exists(self) -> None:
        assert const.DEFAULT_PERGOLA_MODEL in presets.PRESETS

    def test_custom_has_empty_values(self) -> None:
        assert presets.PRESETS[const.DEFAULT_PERGOLA_MODEL]["values"] == {}

    def test_custom_is_default(self) -> None:
        assert const.DEFAULT_PERGOLA_MODEL == "custom"


class TestPresetValuesAreLegalConfigKeys:
    """Every key under `values` must be a recognised geometry-advanced field
    (no typos, no stray cloud or operation knobs)."""

    @pytest.mark.parametrize("model_id", list(presets.PRESETS.keys()))
    def test_no_unknown_keys(self, model_id: str) -> None:
        allowed = set(config_flow._GEOMETRY_ADVANCED_FIELDS)
        actual = set(presets.PRESETS[model_id]["values"].keys())
        unknown = actual - allowed
        assert not unknown, (
            f"{model_id} has values for unknown keys: {unknown}. "
            f"Allowed geometry advanced fields: {allowed}"
        )


class TestPresetValuesInBounds:
    """Every numeric value must fall within the NumberSelector min/max."""

    @pytest.mark.parametrize("model_id", list(presets.PRESETS.keys()))
    def test_values_in_bounds(self, model_id: str) -> None:
        for key, value in presets.PRESETS[model_id]["values"].items():
            lo, hi = _GEOMETRY_BOUNDS[key]
            assert lo <= value <= hi, (
                f"{model_id}.{key} = {value} outside [{lo}, {hi}]"
            )


class TestShippedPresetsVerified:
    """Every preset shipped in this version has source='verified' and a
    non-empty source_url (the exception is `custom`, which is the fallback)."""

    @pytest.mark.parametrize(
        "model_id",
        [m for m in presets.PRESETS if m != const.DEFAULT_PERGOLA_MODEL],
    )
    def test_source_verified(self, model_id: str) -> None:
        assert presets.PRESETS[model_id]["source"] == "verified", (
            f"{model_id} has unexpected source"
        )

    @pytest.mark.parametrize(
        "model_id",
        [m for m in presets.PRESETS if m != const.DEFAULT_PERGOLA_MODEL],
    )
    def test_source_url_present(self, model_id: str) -> None:
        assert presets.PRESETS[model_id]["source_url"].startswith("http"), (
            f"{model_id} source_url should be a URL"
        )


class TestModelChoices:
    """`model_choices()` returns dropdown-ready (value, label) pairs."""

    def test_custom_is_first(self) -> None:
        choices = presets.model_choices()
        assert choices[0]["value"] == const.DEFAULT_PERGOLA_MODEL

    def test_all_models_present(self) -> None:
        choices = presets.model_choices()
        values = {c["value"] for c in choices}
        assert values == set(presets.PRESETS.keys())

    def test_labels_match_display_names(self) -> None:
        for choice in presets.model_choices():
            assert choice["label"] == presets.PRESETS[choice["value"]]["display_name"]


class TestGetPresetValues:
    """The merge helper used by config_flow returns a fresh dict copy."""

    def test_custom_returns_empty(self) -> None:
        assert presets.get_preset_values(const.DEFAULT_PERGOLA_MODEL) == {}

    def test_known_model_returns_max_opening_angle(self) -> None:
        result = presets.get_preset_values("brustor_b200_xl")
        assert result == {const.CONF_MAX_OPENING_ANGLE: 135}

    def test_unknown_model_returns_empty(self) -> None:
        """Unknown ids fall through to integration defaults — never crash."""
        assert presets.get_preset_values("totally_fake_brand_xyz") == {}

    def test_returned_dict_is_a_copy(self) -> None:
        """Mutating the returned dict mustn't poison the registry."""
        d = presets.get_preset_values("brustor_b200_xl")
        d["max_opening_angle"] = 999
        again = presets.get_preset_values("brustor_b200_xl")
        assert again[const.CONF_MAX_OPENING_ANGLE] == 135


class TestKnownPresets:
    """Spot-check the values for each of the 8 verified models against the
    plan's recorded numbers — if someone edits presets.py with the wrong
    value, this catches the regression immediately."""

    @pytest.mark.parametrize(
        ("model_id", "expected_max_angle"),
        [
            ("brustor_b200", 135),
            ("brustor_b200_xl", 135),
            ("brustor_b250", 135),
            ("renson_camargue", 150),
            ("renson_camargue_skye", 135),
            ("renson_algarve", 150),
            ("pratic_vision", 140),
            ("corradi_maestro", 140),
        ],
    )
    def test_max_opening_angle(self, model_id: str, expected_max_angle: int) -> None:
        assert presets.PRESETS[model_id]["values"][const.CONF_MAX_OPENING_ANGLE] == expected_max_angle

    def test_count(self) -> None:
        """v1.15 ships exactly 8 verified presets + custom (9 total)."""
        assert len(presets.PRESETS) == 9
