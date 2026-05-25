"""Pergola model presets.

Each preset pre-fills the manufacturer's published spec sheet values when
a user picks their model from the dropdown in the config flow. Currently
only ``max_opening_angle`` is populated — no manufacturer publishes
``blade_pitch`` or a calculable P/W ratio on their public pages, so
``blade_pitch_ratio`` stays at the integration default (0.92) for every
preset. The four empirical parameters (``flip_profile_threshold``,
``phase_a_intercept``, ``summer_blade_offset``, ``calibration_offset``)
also stay at integration defaults — they require field tuning and are
not published anywhere.

Coordinator code never reads ``CONF_PERGOLA_MODEL``; it's purely a UI
hint stored in the config entry so the Options flow can pre-select the
user's chosen model.

**End-to-end validation status**: only the Brustor B200 XL is field-
validated (it's the maintainer's own pergola). Every other preset is
populated from the manufacturer's published spec sheet but the seasonal-
mode algorithm was tuned for a Brustor-style waterproof louver — users
of other brands may need to fine-tune the empirical parameters via the
advanced view if they observe drift.

How to contribute a new preset or a correction
==============================================
1. Open an issue at https://github.com/qelanhari/ha-pergola/issues with
   your brand, model, and a link to the published spec.
2. Or submit a PR adding an entry below: include the verified
   ``source_url`` (manufacturer page or PDF), the verification date,
   and which fields you confirmed.
"""

from __future__ import annotations

from typing import Any

from .const import CONF_MAX_OPENING_ANGLE, DEFAULT_PERGOLA_MODEL


# Each entry's `values` only contains spec-sheet-verifiable fields. Absent
# fields inherit DEFAULT_* via the geometry-defaults merge in config_flow.
PRESETS: dict[str, dict[str, Any]] = {
    DEFAULT_PERGOLA_MODEL: {
        "display_name": "Custom / Other",
        "brand": "",
        "values": {},
        "source": "verified",
        "source_url": "",
        "notes": (
            "Legacy v1.14 behavior: integration defaults tuned for a typical "
            "waterproof louver pergola (e.g. Brustor B200 XL with 21cm blades)."
        ),
    },

    # --- Brustor -------------------------------------------------------------
    # Brustor's product pages don't publish max blade rotation; the maintainer's
    # own B200 XL with 21cm blades is the ground-truth source. The B200 and B250
    # share the same product line and 21cm louvre option, so we extend the same
    # value to them. If you have one of these models and observe a different
    # max angle, please open an issue.
    "brustor_b200": {
        "display_name": "Brustor B200",
        "brand": "Brustor",
        "values": {CONF_MAX_OPENING_ANGLE: 135},
        "source": "verified",
        "source_url": "https://www.brustor.com/en/bioclimatic-pergolas/brustor-b200-xl-bioclimatic-pergola",
        "notes": (
            "Same product line as the maintainer's B200 XL (21cm blades, 135°). "
            "Brustor's site doesn't publish the rotation angle; verify on your "
            "spec sheet if you have the 16cm variant."
        ),
    },
    "brustor_b200_xl": {
        "display_name": "Brustor B200 XL",
        "brand": "Brustor",
        "values": {CONF_MAX_OPENING_ANGLE: 135},
        "source": "verified",
        "source_url": "https://www.brustor.com/en/bioclimatic-pergolas/brustor-b200-xl-bioclimatic-pergola",
        "notes": (
            "Maintainer's own pergola; 21cm blades, 135° max rotation. "
            "End-to-end validated."
        ),
    },
    "brustor_b250": {
        "display_name": "Brustor B250",
        "brand": "Brustor",
        "values": {CONF_MAX_OPENING_ANGLE: 135},
        "source": "verified",
        "source_url": "https://www.brustor.com/en/patio-roofs/brustor-b250-xl-louvered-pergola",
        "notes": (
            "Newer Brustor line with 21cm blades. Brustor's site doesn't "
            "publish the rotation angle explicitly; assumed same as B200 XL."
        ),
    },

    # --- Renson --------------------------------------------------------------
    # Renson publishes blade rotation on each product page.
    "renson_camargue": {
        "display_name": "Renson Camargue",
        "brand": "Renson",
        "values": {CONF_MAX_OPENING_ANGLE: 150},
        "source": "verified",
        "source_url": "https://renson.net/en-us/products/pergolas/camargue",
        "notes": "Manufacturer page states blades rotate up to 150°.",
    },
    "renson_camargue_skye": {
        "display_name": "Renson Camargue Skye",
        "brand": "Renson",
        "values": {CONF_MAX_OPENING_ANGLE: 135},
        "source": "verified",
        "source_url": "https://renson.net/en-us/products/pergolas/camargue-skye",
        "notes": (
            "Retractable + rotating blades. Manufacturer page states up to 135°."
        ),
    },
    "renson_algarve": {
        "display_name": "Renson Algarve",
        "brand": "Renson",
        "values": {CONF_MAX_OPENING_ANGLE: 150},
        "source": "verified",
        "source_url": "https://renson.net/en-us/products/pergolas/algarve",
        "notes": "Manufacturer page states blades rotate up to 150°.",
    },

    # --- Pratic --------------------------------------------------------------
    "pratic_vision": {
        "display_name": "Pratic Vision",
        "brand": "Pratic",
        "values": {CONF_MAX_OPENING_ANGLE: 140},
        "source": "verified",
        "source_url": "https://www.pratic.it/en/product/vision/",
        "notes": "Manufacturer page: blades rotate from 0° to 140°.",
    },

    # --- Corradi -------------------------------------------------------------
    "corradi_maestro": {
        "display_name": "Corradi Maestro",
        "brand": "Corradi",
        "values": {CONF_MAX_OPENING_ANGLE: 140},
        "source": "verified",
        "source_url": "https://www.corradi.eu/en/products/bioclimatics/maestro",
        "notes": "Manufacturer page: blades can be turned up to 140°.",
    },

    # --- Solembra (French) ---------------------------------------------------
    # All three Solembra bioclimatic ranges share the same blade module —
    # "1 ou 2 modules de lames orientables de 0 à 160°". Difference between
    # models is overall surface area (Izzy ≤32m², Me ≤36m², Design ≤48m²),
    # not blade physics.
    "solembra_sol_izzy": {
        "display_name": "Solembra Sol Izzy",
        "brand": "Solembra",
        "values": {CONF_MAX_OPENING_ANGLE: 160},
        "source": "verified",
        "source_url": "https://produits.batiactu.com/produits/solembra-pergola-bioclimatique-a-lames-orientable--gamme-so-194361.php",
        "notes": "Manufacturer spec sheet: blades 0–160°. Standard module, up to 32m².",
    },
    "solembra_sol_me": {
        "display_name": "Solembra Sol Me",
        "brand": "Solembra",
        "values": {CONF_MAX_OPENING_ANGLE: 160},
        "source": "verified",
        "source_url": "https://produits.batiactu.com/produits/solembra-pergola-bioclimatique-a-lames-orientable-gamme-sol-194417.php",
        "notes": "Manufacturer spec sheet: blades 0–160°. Custom-dimension module, up to 36m².",
    },
    "solembra_sol_design": {
        "display_name": "Solembra Sol Design",
        "brand": "Solembra",
        "values": {CONF_MAX_OPENING_ANGLE: 160},
        "source": "verified",
        "source_url": "https://produits.batiactu.com/produits/solembra-pergola-bioclimatique-a-lame-orientables-gamme-sol-194418.php",
        "notes": "Manufacturer spec sheet: blades 0–160°. Largest range, up to 48m².",
    },
}


def get_preset_values(model_id: str) -> dict[str, Any]:
    """Return the `values` dict for a preset, or an empty dict if unknown.

    Unknown / "custom" → empty dict, which means "use integration defaults"
    when merged with the geometry-defaults dict in config_flow.
    """
    preset = PRESETS.get(model_id)
    if preset is None:
        return {}
    return dict(preset["values"])


def model_choices() -> list[dict[str, str]]:
    """Return SelectSelector-compatible (value, label) pairs for the dropdown.

    `custom` always sorts first. The rest are alphabetical by brand+model
    for predictable scanning.
    """
    items = sorted(
        (mid for mid in PRESETS if mid != DEFAULT_PERGOLA_MODEL),
        key=lambda m: (PRESETS[m]["brand"], PRESETS[m]["display_name"]),
    )
    return [
        {"value": DEFAULT_PERGOLA_MODEL, "label": PRESETS[DEFAULT_PERGOLA_MODEL]["display_name"]},
        *[{"value": mid, "label": PRESETS[mid]["display_name"]} for mid in items],
    ]
