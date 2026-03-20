# Bioclimatic Pergola — Home Assistant Blueprint

A Home Assistant blueprint to automatically control bioclimatic pergola slats
based on solar position, with optional cloud detection via PV power, optional
humidity blocking, and daily mechanical calibration.

## Quick import

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fqelanhari%2Fha-pergola%2Fblob%2Fmain%2Fblueprints%2Fpergola_bioclimatique.yaml)

Or manually: **Settings → Automations → Blueprints → Import blueprint**.

---

## How it works

### Winter mode

The goal is to **capture maximum direct sunlight**.

`profile_angle` encodes the full geometry (elevation + azimuth relative to the
pergola face): it peaks when the sun directly faces the pergola, then decreases.

By applying `max(solar_percent, current_position)` at every cycle, the pergola
**rises with the solar profile** in the morning and **naturally holds its peak
position** in the afternoon when the sun moves behind — no azimuth condition needed.

```
Morning   : profile_angle rises  →  15% → 30% → 60% → 80%
Peak      : profile_angle at max  →  80%
Afternoon : profile_angle falls, max() holds  →  80% → 80% → 80%
Sun too low (< standby threshold)  →  60%
```

### Summer mode

The goal is to **fully block direct radiation**.

Slats orient in full opposition to the sun (+90°). The full range (0→100%) is
used before flipping. As soon as 100% can no longer block the sun
(`s_raw > max_opening_angle`), the slats immediately jump to the other extreme
(~0%) — no progressive descent.

```
Morning  : s_raw ≤ 135°  →  ~67% → 100%
Peak     : s_raw = 135°  →  100%
Flip (s_raw > 135°)      →  ~0%
Standby / overcast        →  60%
```

### Cloud detection

If a PV power sensor is configured, cloud detection uses a smoothed power
reading (exponential filter α = 0.4) compared to a dynamic threshold based on
the angle of incidence. A 15-minute lock prevents oscillations during fast
cloud cover changes.

**Without a PV sensor**, the pergola always follows the solar target; standby
still activates when the sun is too low.

### Morning calibration

Once per day, at the first cycle where the pergola would move, the slats fully
close (mechanical zero reference), wait 45 s, then resume the calculated
position. The calibration date is stored in an `input_text` helper to avoid
repeating it within the same day.

---

## Prerequisites

### Sun integration

The built-in **Sun** integration must be active (enabled by default). It
provides `sensor.sun_solar_azimuth` and `sensor.sun_solar_elevation`,
used as default values in the blueprint.

### Required helpers

Create these in **Settings → Devices & Services → Helpers**:

| Suggested name | Type | Role |
|---|---|---|
| `input_select.pergola_mode` | Select | Options: Winter, Summer, Manual (labels are configurable) |
| `input_text.pergola_last_calibration` | Text | Stores calibration date (YYYY-MM-DD) |
| `input_boolean.pergola_ready` | Toggle | Enabled by the companion automation post-calibration |

### Optional helpers

Only needed if you configure PV-based cloud detection:

| Suggested name | Type | Role |
|---|---|---|
| `input_number.pergola_pv_smooth` | Number (0–5000, step 0.1) | Smoothed PV power between cycles |
| `input_boolean.pergola_sunny` | Toggle | Current sunny state (with 15-min hysteresis) |

### Companion automations

Copy the two files from the `automations/` folder into your HA config and adapt
entity names to match your setup:

| File | Role |
|---|---|
| `pergola_reset_morning_lock.yaml` | Resets `pergola_ready` to off every night at midnight |
| `pergola_unlock_after_calibration.yaml` | Enables `pergola_ready` once calibration is done and sun > 20° |

> The unlock automation includes an optional priority lock condition.
> Remove it if you do not use a lock sensor.

---

## Installation

1. Create the required helpers listed above.
2. Import the blueprint (button above or manual URL).
3. Create an automation from the blueprint and fill in the form.
4. Copy and adapt the two companion automations.
5. Enable all automations.

---

## Blueprint parameters

### Geometry

| Parameter | Default | Description |
|---|---|---|
| Face azimuth | `180°` | Direction the slats face at 100% open. 180° = South. |
| Maximum slat angle | `135°` | Physical angle corresponding to 100% opening. |
| Calibration offset | `0°` | Permanent mechanical correction. Adjust after observation. |
| Summer safety margin | `10°` | Extra angle in Summer to guarantee shade at the flip point. |

### Behaviour

| Parameter | Default | Description |
|---|---|---|
| Position step size | `5%` | Target position resolution. Reduces unnecessary movements. |
| Standby / overcast position | `60%` | Position when overcast or sun too low. |
| Standby threshold | `9%` | Below this computed %, sun is too low → standby. |
| Minimum solar elevation | `5°` | Below this elevation the automation does not run. |

### Optional sensors

| Parameter | Default | Description |
|---|---|---|
| Humidity sensor | *(empty)* | If set, blocks the automation above the configured threshold. |
| Humidity blocking threshold | `80%` | Only relevant when a humidity sensor is configured. |
| Priority lock sensor | *(empty)* | If set, blocks the automation when state is `rain`, `temperature`, or `security`. |
| PV power sensor | *(empty)* | If set, enables cloud detection. Leave empty to always track the sun. |
| PV smooth helper | *(empty)* | Required when using a PV sensor. |
| Sunny state helper | *(empty)* | Required when using a PV sensor. |
| Estimated peak PV power | `3000 W` | Used to compute the dynamic sunny threshold. |

---

## Calibrating the offset

After installation, observe the pergola on a clear sunny morning:

- Slats seem **too closed** → increase `calibration_offset` (less negative).
- Slats seem **too open** → decrease `calibration_offset` (more negative).

Adjust, trigger the automation manually, observe. Repeat until slats are
perpendicular to direct sunlight at solar noon.

---

## Troubleshooting

**Pergola does not move at all**
→ Check that `pergola_ready` is `on`. If not, the unlock companion automation
has not run yet — wait for the sun to rise above 20°.

**Pergola stays at 60% even in full sun (with PV sensor)**
→ The smoothed PV power does not exceed the dynamic threshold. Check the PV
sensor entity and increase `pv_max_w` to lower the threshold.

**Pergola oscillates in Summer mode**
→ `s_raw` is hovering around `max_opening_angle`. Increase
`summer_safety_offset` by 5° to shift the flip point.

**Calibration fails** (slats do not reach 0%)
→ Check for mechanical blockage and confirm the cover entity responds to
`cover.close_cover_tilt`.

---

## Repository structure

```
ha-pergola/
├── blueprints/
│   └── pergola_bioclimatique.yaml          # Main blueprint (one-click HA import)
└── automations/
    ├── pergola_reset_morning_lock.yaml
    └── pergola_unlock_after_calibration.yaml
```
