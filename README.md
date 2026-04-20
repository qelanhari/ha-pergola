# Pergola Bioclimatique — Home Assistant Custom Integration

A Home Assistant custom integration that automatically controls bioclimatic pergola slats based on solar position, with optional cloud detection, humidity blocking, safety locks, and daily mechanical calibration.

**Replaces the previous blueprint + automations approach** with a single, self-contained device — no helpers needed.

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS.
2. Install "Pergola Bioclimatique".
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration > Pergola Bioclimatique**.

### Manual

Copy the `custom_components/pergola_bioclimatique/` folder into your Home Assistant `config/custom_components/` directory and restart.

---

## Prerequisites

### Sun integration

The integration requires the **Sun** integration to be configured in Home Assistant. It provides solar azimuth and elevation sensors needed for slat positioning.

The config flow automatically detects `sensor.sun_solar_azimuth` and `sensor.sun_solar_elevation`. If you use a different source (Sun2, Astral, etc.), you can select any sensor entities manually.

---

## Configuration

The setup wizard guides you through 4 steps:

### Step 1: Entity selection

| Parameter | Required | Description |
|---|---|---|
| Pergola cover entity | Yes | The cover entity whose tilt is controlled |
| Sun azimuth sensor | Yes | Auto-detected from Sun integration |
| Sun elevation sensor | Yes | Auto-detected from Sun integration |
| PV power sensor | No* | For cloud detection via solar power |
| Light sensor | No* | Alternative cloud detection via luminosity |
| Humidity sensor | No | Blocks automation above threshold |
| Safety lock sensor | No | Monitors rain/temperature/security locks |
| Safety lock timer | No | Duration of safety locks |

*At least one of PV or light sensor is recommended for cloud detection. Without either, the pergola always follows the solar target.

### Step 2: Geometry

| Parameter | Default | Description |
|---|---|---|
| Face azimuth | 130° | Compass direction the pergola faces (0°=N, 90°=E, 180°=S) |
| Maximum opening angle | 135° | Physical angle corresponding to 100% tilt |
| Calibration offset | -10° | Permanent mechanical correction |
| Summer safety margin | 10° | Extra shading margin in summer mode |

### Step 3: Operation

| Parameter | Default | Description |
|---|---|---|
| Update interval | 5 min | Control loop frequency |
| Step size | 5% | Position quantization (reduces mechanical wear) |
| Deadband | 2% | Minimum change to trigger movement |
| Cloudy/standby position | 60% | Default position when overcast |
| Minimum useful position | 9% | Below this, switch to standby |
| Humidity threshold | 80% | Block automation above this humidity |
| Minimum elevation | 20° | Below this sun elevation, control loop and morning calibration are inactive |

### Step 4: Cloud detection (only if PV/light sensor configured)

| Parameter | Default | Description |
|---|---|---|
| PV maximum power | 3000 W | Peak power under ideal conditions |
| PV panel azimuth | 180° | Compass direction the panels face (0°=N, 180°=S) |
| PV panel tilt | 30° | Panel tilt from horizontal (0°=flat, 90°=vertical) |
| Sunny threshold ratio | 0.70 | Fraction of modelled clear-sky power above which it's sunny |
| Smoothing coefficient | 0.4 | Reactivity (higher = more reactive) |
| Hysteresis duration | 900 s | Minimum time before state switch |

All parameters from steps 2-4 can be modified at runtime via **Options** without restarting.

---

## How it works

### Modes

- **Hiver (Winter):** Follows the sun upward, holds peak position when sun descends. Maximizes direct sunlight.
- **Ete (Summer):** Orients slats in full opposition (+90°). Flips to ~0% when max angle exceeded. Maximizes shade.
- **Manuel (Manual):** Control loop disabled. Full manual control.

### Solar geometry

The integration computes a `profile_angle` from sun elevation and azimuth relative to the pergola face orientation. This angle drives the target tilt position.

### Cloud detection

When a PV or light sensor is configured, exponential smoothing with a dynamic threshold detects sunny/cloudy conditions. The threshold is `ratio × pv_max × cos(angle_of_incidence)` using the configured panel azimuth and tilt, floored at 400 W — so it scales naturally with sun position through the day and across seasons. A configurable hysteresis (default 15 min) prevents rapid oscillations.

### Morning calibration

Each day, when sun elevation exceeds the calibration threshold:
1. Slats close fully (mechanical zero reference)
2. Wait 45 seconds
3. Verify position < 5%
4. Unlock for the day

### Safety watchdog

When a safety lock is active (rain/temperature/security):
- **Temperature/security:** Force close
- **Rain:** Hold current position
- Resumes normal operation when lock clears

---

## Exposed entities

All entities appear under a single "Pergola Bioclimatique" device:

### Sensors
- **Profile Angle** — Solar profile angle in degrees
- **Solar Target** — Computed solar target position (%)
- **Final Target** — Actual target after all logic (%)
- **PV Smooth** — Smoothed PV power reading (W) *(if PV configured)*

### Binary sensors
- **Ready** — Unlocked after morning calibration
- **Calibrated Today** — Whether calibration was done today
- **Sunny** — Current sun/cloud state *(if PV/light configured)*

### Select
- **Mode** — Hiver / Ete / Manuel

---

## Calibrating the offset

After installation, observe the pergola on a clear morning:

- Slats too closed → increase calibration offset (less negative)
- Slats too open → decrease calibration offset (more negative)

Adjust via Options, the integration applies changes immediately.

---

## Troubleshooting

**Pergola does not move**
Check that the "Ready" binary sensor is on. If not, wait for sun elevation to exceed the calibration threshold.

**Stays at 60% in full sun (with PV sensor)**
The smoothed PV power is below the threshold. Check the PV sensor and adjust PV max watts or sunny ratio in Options.

**Oscillates in summer mode**
Increase the summer safety margin by 5° in Options.

**Calibration fails**
Check for mechanical blockage and confirm the cover entity responds to `cover.close_cover_tilt`.

---

## Repository structure

```
ha-pergola/
├── custom_components/
│   └── pergola_bioclimatique/
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── coordinator.py
│       ├── solar.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── select.py
│       ├── const.py
│       ├── strings.json
│       └── translations/
│           └── fr.json
├── tests/
│   ├── conftest.py
│   └── test_solar.py
├── hacs.json
└── README.md
```
