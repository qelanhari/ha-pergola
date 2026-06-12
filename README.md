# Pergola Bioclimatique — Home Assistant Custom Integration

Automatic control of bioclimatic pergola slats based on solar position. Tilts the blades to track the sun in winter (maximize sunlight) or block it in summer (maximize shade), with optional cloud detection, humidity blocking, safety locks, and daily mechanical calibration.

A single self-contained device — no helpers, no manual automations, no YAML.

---

## Install via HACS

1. In HACS, add this repository as a custom repository (Integration).
2. Install **Pergola Bioclimatique**, then restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Pergola Bioclimatique**.

Manual install: copy `custom_components/pergola_bioclimatique/` into your Home Assistant `config/custom_components/` directory and restart.

---

## For everyday users

You don't need to know anything about blade geometry, profile angles, or solar trigonometry to use this integration. The defaults are pre-tuned for a typical waterproof louver pergola — just give it your cover entity and the direction your pergola faces.

### Quick setup (2 minutes)

The setup wizard has 3 mandatory steps (4 if you wire up cloud detection). All advanced knobs are hidden behind a **Show advanced settings** checkbox — leave it unticked unless you have a specific reason to tune.

1. **Pick the pergola and its sensors.** Choose your cover entity and the Sun integration sensors (auto-detected). PV/light/humidity/safety-lock sensors are optional.
2. **Pergola model and facing direction.** Pick your pergola model from the dropdown if it's listed (the manufacturer's published specs get filled in automatically); otherwise pick *Custom / Other*. Then enter the compass bearing the pergola faces.
3. **Operation.** How often to run, default standby position, humidity limit. Defaults are fine.
4. **Cloud detection** *(only if you picked a PV or light sensor)*. Enter your inverter's nameplate peak power. Defaults are fine for the rest.

That's it. The pergola will calibrate on the next sunny morning and start tracking the sun.

#### Supported pergola models

The dropdown ships with these presets — each fills in the manufacturer's published maximum blade rotation angle so you don't have to look it up:

- **Brustor** B200, B200 XL, B250 — 135° max rotation
- **Renson** Camargue — 150°; Camargue Skye — 135°; Algarve — 150°
- **Pratic** Vision — 140°
- **Corradi** Maestro — 140°
- **Solembra** Sol Izzy, Sol Me, Sol Design — 160° (added in v1.16)

**⚠ Only the Brustor B200 XL has been tested end-to-end on real hardware** (it's the maintainer's own pergola). Every other preset is populated from the manufacturer's published spec sheet but hasn't been field-validated. The seasonal-mode algorithm was tuned for Brustor-style waterproof louvers — users of other brands may need to fine-tune `blade_pitch_ratio`, `flip_profile_threshold`, `phase_a_intercept`, or `summer_blade_offset` via the advanced settings if behavior drifts. **If you spot a spec error or want a preset added/adjusted, please [open an issue](https://github.com/qelanhari/ha-pergola/issues) with your model and the correction.**

### How to find your facing direction

Stand under your pergola facing **outward** (the direction the sun comes from that you want shade from). Open your phone's compass app and read the bearing. That number — in degrees from North — is your facing direction.

Rough values for reference:
- North = 0°
- East = 90°
- South = 180°
- West = 270°

A south-facing pergola is `180`, a southeast-facing one is `135`, southwest is `225`, etc.

### Optional sensors — what each one adds

You can configure the integration with just the cover and sun sensors. Adding the optional sensors unlocks extra behaviors:

- **PV power sensor** — Detects when it's cloudy. When the sky goes overcast, the pergola moves to its standby position instead of chasing a sun that isn't there. Removes pointless movements on bad-weather days.
- **Outdoor light sensor (lux)** — Same purpose as PV power, but using a luminosity reading. Use whichever you have; both work together if you have both.
- **Humidity sensor** — Pauses the automation when humidity is too high. Useful for protecting motors during storms or heavy condensation.
- **Safety lock sensor** — If you already have safety automations (rain/wind/temperature locks), the integration will defer to them: close on hot/security alarms, hold position on rain.

### Daily use

After install, the integration exposes one **device** with several entities:

| Entity | What it does |
|---|---|
| `select.pergola_mode` | Switch between **Hiver** (winter, follow the sun), **Été** (summer, block the sun), and **Manuel** (automation off). |
| `button.pergola_recalibrate` | Force a full close-and-verify calibration cycle. Use after a power outage or if the cover drifted. |
| `button.pergola_refresh_target` | Trigger an immediate control loop run. Handy when tweaking settings. |
| `binary_sensor.pergola_ready` | Lit once the morning calibration has run. The pergola won't move until this is on. |
| `binary_sensor.pergola_calibrated_today` | Whether today's calibration has already happened. |
| `binary_sensor.pergola_sunny` | Live sunny/cloudy state (only if PV/light sensor configured). |
| `binary_sensor.pergola_movement_problem` | Lit when a recent movement failed to reach its target — check for mechanical blockage. |
| `sensor.pergola_profile_angle` | The current sun profile angle relative to the pergola face (degrees). Useful for calibration. |
| `sensor.pergola_solar_target` | The position the geometry says is optimal (%). |
| `sensor.pergola_final_target` | The position actually commanded after all overrides (%). |

### Modes

- **Hiver (Winter)** — Slats track the sun upward as it rises, then hold the highest position when the sun descends. Maximizes direct sunlight.
- **Été (Summer)** — Slats follow the sun's profile angle to block direct rays while preserving airflow and diffuse light. Flips blade side at midday.
- **Manuel (Manual)** — Control loop disabled. You're in charge.

Switch modes at any time via the **Mode** select. Switching to **Manuel** stops all automatic movement; switching back resumes from the next control tick.

### Troubleshooting

**The "Ready" sensor never turns on.** The morning calibration only runs once the sun rises above the configured minimum elevation (default 20°). Check that your sun elevation sensor is reporting a value and that the sun is actually that high — at higher latitudes in winter, it may not be. You can also press **Recalibrate** to force it.

**The pergola doesn't move at all.** Check that **Ready** is on, **Mode** isn't set to Manuel, and humidity isn't over the threshold (default 80%). If a safety lock is active, that takes priority — look at the lock entity's state.

**Pergola stays at 60% even though it's clearly sunny.** If you have a PV power sensor configured, the integration is in "cloudy" mode — your smoothed PV reading is below the sunny threshold. Check `sensor.pergola_pv_smooth` against the inverter's actual reading. You may need to adjust the peak PV power in Options if your inverter is much smaller than 3000 W default.

**Pergola flickers between positions on a partly cloudy day.** The hysteresis duration (default 15 minutes) should already smooth this out. If it's still flickering, the issue is more likely your sensor — try the lux/PV combination if you only have one.

**Blades close too late in the morning.** That's `sun_az_min` — by default the facing direction − 90°, but if your building's wall shadows the pergola for longer, tighten it. Open **Settings → Devices & Services → Pergola Bioclimatique → Configure → Show advanced settings** to adjust.

**Blades jump open in the late afternoon while the sun is still hitting the pergola.** In summer mode the blades ramp up to the perpendicular/cloudy resting position on their own — if they jump there early instead, your `sun_az_max` is too low: the integration thinks the building already shadows the pergola and stops sun-tracking. Widen `sun_az_max` (advanced settings) so the window only closes once the sun is genuinely behind the structure.

**Blades close too much / not enough in summer.** Tweak `summer_blade_offset` in advanced settings. Positive value = more closure on the afternoon side; negative = less.

**Movement Problem sensor is lit.** A recent `set_cover_tilt_position` didn't land within tolerance. Check for mechanical blockage on the cover, confirm the entity responds to manual tilt commands, then press Recalibrate.

---

## For advanced users

Every default is intentional. The integration is pre-tuned for a typical aluminium waterproof louver pergola with a `0.92` blade pitch/width ratio and a `135°` mechanical max. If your hardware is different, or you want to dial in calibration precisely, read on.

### Pergola model presets

The setup wizard's "Pergola model" dropdown picks from a small registry of brand+model entries in [`presets.py`](custom_components/pergola_bioclimatique/presets.py). In v1.15 each shipped preset sets a single field: `max_opening_angle` (the mechanical blade tilt corresponding to 100% on the cover entity). Everything else stays at the integration's tuned defaults — manufacturers don't publish blade pitch, flip threshold, or any of the empirical parameters that come from field observation.

| Preset | Verified `max_opening_angle` | Source |
|---|---|---|
| Brustor B200 / B200 XL / B250 | 135° | Maintainer's B200 XL with 21cm blades |
| Renson Camargue | 150° | [renson.net](https://renson.net/en-us/products/pergolas/camargue) |
| Renson Camargue Skye | 135° | [renson.net](https://renson.net/en-us/products/pergolas/camargue-skye) |
| Renson Algarve | 150° | [renson.net](https://renson.net/en-us/products/pergolas/algarve) |
| Pratic Vision | 140° | [pratic.it](https://www.pratic.it/en/product/vision/) |
| Corradi Maestro | 140° | [corradi.eu](https://www.corradi.eu/en/products/bioclimatics/maestro) |
| Solembra Sol Izzy / Sol Me / Sol Design | 160° | Manufacturer spec sheets via [batiactu.com](https://produits.batiactu.com/) — all three Solembra ranges share the same 0–160° blade module |

**End-to-end validation status**: only the Brustor B200 XL is field-validated. Other entries are taken at face value from the manufacturer's product page. The seasonal-mode algorithm itself was tuned on a Brustor-style waterproof louver pergola; non-Brustor users may need to tweak `flip_profile_threshold`, `phase_a_intercept`, and `summer_blade_offset` via the advanced view if they observe drift.

#### Contributing a correction or a new preset

If your pergola isn't listed, or a value is wrong for your installation:

1. **Quick path**: [open an issue](https://github.com/qelanhari/ha-pergola/issues) with your brand, model, and a link to the published spec sheet (or your own measurement). I'll add it to the next release.
2. **PR path**: append your entry to `custom_components/pergola_bioclimatique/presets.py`, run `pytest tests/test_presets.py`, and open a PR. Include the source URL in the entry's `source_url` field.

### Architecture

The integration is a single-device integration built around one `DataUpdateCoordinator`. All entities are thin views over `coordinator.data`. Pure solar math lives in `solar.py` (no Home Assistant imports — runs standalone and is exercised by `tests/test_solar.py`).

```
custom_components/pergola_bioclimatique/
├── __init__.py            — entry setup / unload / options reload
├── manifest.json          — version, HACS metadata
├── coordinator.py         — the brain: control loop, calibration, persistence
├── solar.py               — pure functions (compute_profile_angle, *_target, …)
├── config_flow.py         — install wizard + Options flow (basic/advanced)
├── const.py               — every CONF_* / DEFAULT_*
├── presets.py             — pergola model preset registry
├── select.py / sensor.py / binary_sensor.py / button.py — entity surface
├── strings.json + translations/{en,fr}.json
```

See [CLAUDE.md](CLAUDE.md) for full architecture and control-loop details.

### Control loop logic

Each tick (`update_interval`, default 5 min) the coordinator:

1. Reads sun azimuth/elevation, optional PV/light/humidity, safety-lock states.
2. Computes a **profile angle** (sun's angle relative to the pergola face) and a **solar target** in % via `solar.py`.
3. Applies overrides in priority order:
   - **Safety lock** active → close (temperature/security) or hold (rain).
   - **Not-yet-calibrated** → don't move; wait for morning calibration.
   - **Humidity over threshold** → pause.
   - **Outside sun exposure window** (`sun_az_min` / `sun_az_max`) → fall back to `cloudy_target` (building itself shadows the pergola).
   - **Cloudy** → fall back to `cloudy_target`; in winter, hold the previously commanded position if higher.
   - **Solar target < min_useful_percent** → fall back to `cloudy_target` (twilight standby guard).
   - Otherwise → use the **solar target**.
4. Quantizes by `step_size` and applies the `deadband` before issuing `cover.set_cover_tilt_position` (or `open_cover_tilt` / `close_cover_tilt` at the 0% / 100% extremes — preserves mechanical calibration).

State that must survive restarts (last calibration date, cloud hysteresis state, smoothed PV, last commanded position) is persisted to `Store` every cycle.

### Winter mode — follow and hold

`compute_winter_target(profile_angle, calibration_offset, current_pos, max_opening_angle, step_size)`:

```
raw_angle = profile_angle + calibration_offset
percent = (raw_angle / max_opening_angle) × 100
return max(quantize(percent, step_size), current_pos)
```

The `max(…, current_pos)` keeps the position from descending as the sun sets, holding the peak target reached for the day.

### Summer mode — two-phase

`compute_summer_target(profile_angle, calibration_offset, max_opening_angle, step_size, pitch_ratio, flip_profile_threshold, summer_blade_offset, phase_a_intercept, cloudy_target=None)`:

**Phase A** (profile_angle < flip_threshold) — **linear ramp**:
```
target_pct = phase_a_intercept + (100 - phase_a_intercept) × (profile / flip_threshold)
```
Theoretical cutoff geometry has the wrong slope for real blades; field observation showed a linear ramp matches reality across the whole pre-bascule range.

**Phase B** (profile_angle ≥ flip_threshold) — **cutoff geometry**:
```
δ = arccos(pitch_ratio × sin(profile))
blade_angle = profile - 90 + δ + calibration_offset + summer_blade_offset
target_pct = (blade_angle / max_opening_angle) × 100
```
Quantized by `step_size`. If `blade_angle ≤ 0` (degenerate edge case just after the flip) → 100% (max opening).

**Phase B cap** — perpendicular blades (90° of `max_opening_angle`, ≈ 67% at 135°) are the last position that still casts shade; past it the raw geometry keeps opening toward 100% while tracking sun the blades can no longer block. So phase B is capped at `min(cloudy_target, perpendicular)` (quantized): the blades ramp up to the cap through the afternoon and rest there. `cloudy_target` can only lower the resting point, never push tracking past perpendicular. (The coordinator always passes `cloudy_target`; calling the function without it gives the raw uncapped curve.)

### Cloud detection

Decided by `is_sunny(pv_smooth, pv_threshold, pv_observable, lux_smooth, lux_threshold, lux_observable, previous_is_sunny)` in `solar.py`. Logic:

- **OR-combine** observable votes: PV says sunny OR lux says sunny → sunny.
- **Observability gates**: PV only counts when `cos(angle_of_incidence)` on the panel exceeds `pv_observable_cos` (panel must actually see the sun). Lux only counts when sun azimuth is in `[lux_az_min, lux_az_max]` (lux sensor must see direct sun).
- **Blind spot**: if neither sensor is observable, hold the previous `is_sunny` state — don't go cloudy just because the geometry is unfavorable.
- **Hysteresis**: minimum `hysteresis_duration` seconds between state flips (default 15 min). Prevents flickering during scattered clouds.

The PV "sunny" threshold is dynamic: `pv_threshold = max(0, cos(AoI)) × pv_max × pv_sunny_ratio`, where AoI depends on the configured panel azimuth / tilt and the current sun position.

### Morning calibration

When sun elevation crosses `min_elevation` and `ready` is False:

1. Check the persisted `last_known_position` (the last position the integration successfully commanded yesterday).
2. **Drift skip optimization**: if the current cover position is within `deadband` of `last_known_position`, no drift could have happened overnight — mark today as calibrated without moving. Saves wear on days the position would have been identical anyway.
3. Otherwise, close fully, wait 45 s, verify position < 5%, mark calibrated.

### Safety lock watchdog

Subscribes to state changes on `priority_lock_entity`. When a lock origin appears:

- **Temperature** / **security** → close immediately and wait 75 s before resuming.
- **Rain** → hold current position (don't drift when wet).

Resumes normal operation when the lock clears.

### Parameter reference

#### Geometry (Step 2 → advanced)

| Parameter | Default | Range | Description |
|---|---|---|---|
| `face_azimuth` | 130° | 0–360 | Compass direction the pergola faces. |
| `max_opening_angle` | 135° | 90–180 | Mechanical blade tilt at 100%. |
| `calibration_offset` | -10° | -30 to +30 | Permanent mechanical correction added to computed blade angle. |
| `blade_pitch_ratio` | 0.92 | 0.5–1.2 | Blade pitch (centre-to-centre) ÷ blade width. Drives the phase B cutoff curve. |
| `flip_profile_threshold` | 80° | 60–90 | Profile angle at which summer blades flip from side A (clamped 100%) to side B (cutoff geometry). |
| `summer_blade_offset` | 0° | -30 to +30 | Additional blade-angle correction applied to phase B only. Positive = closer afternoon side. |
| `phase_a_intercept` | 40% | 0–80 | Target % at profile=0 for the linear morning ramp. |
| `sun_az_min` | face-90° | 0–360 | Below this sun azimuth, building shadows the pergola → fall back to cloudy_target. |
| `sun_az_max` | face+90° | 0–360 | Above this sun azimuth, building shadows the pergola → fall back to cloudy_target. Keep it wide: the summer phase-B cap handles the normal end-of-afternoon resting; this is only the building-shadow guard. |

#### Operation (Step 3)

| Parameter | Default | Range | Description |
|---|---|---|---|
| `update_interval` | 5 min | 1–30 | Control loop period. |
| `step_size` | 5% | 1–10 | Position quantization (reduces mechanical wear). |
| `deadband` | 2% | 1–10 | Minimum change to trigger a movement. |
| `cloudy_target` | 60% | 0–100 | Position when cloudy / in standby / outside sun-exposure window. Also caps the summer phase-B ramp (bounded by perpendicular blades — see Summer mode). |
| `min_useful_percent` | 9% | 0–30 | Below this solar target, switch to cloudy_target (twilight guard). |
| `humidity_max` | 80% | 50–100 | Above this humidity, automation is paused. |
| `min_elevation` | 20° | 5–40 | Below this sun elevation, control loop and morning calibration stay idle. |

#### Cloud detection (Step 4 → advanced; only if PV or light sensor configured)

| Parameter | Default | Range | Description |
|---|---|---|---|
| `pv_max_watts` | 3000 W | 100–20000 | Inverter peak power under ideal conditions. |
| `pv_panel_azimuth` | = face_azimuth | 0–360 | Compass direction PV panels face. Override if panels are on a different roof slope. |
| `pv_panel_tilt` | 30° | 0–90 | PV panel tilt from horizontal. |
| `pv_sunny_ratio` | 0.50 | 0.1–1.0 | Fraction of modelled clear-sky power above which sky is sunny. |
| `pv_smooth_alpha` | 0.4 | 0.1–0.9 | Exponential smoothing weight (higher = more reactive). |
| `hysteresis_duration` | 900 s | 60–3600 | Minimum time before flipping sunny/cloudy state. |
| `lux_sunny_ratio` | 25000 lx | 1000–100000 | Lux threshold (applies sin(elevation) factor). |
| `pv_observable_cos` | 0.4 | 0.0–0.9 | Min cos(AoI) on panel for PV to vote. |
| `lux_az_min` | 120° | 0–360 | Lux observable: min sun azimuth. |
| `lux_az_max` | 260° | 0–360 | Lux observable: max sun azimuth. |

All steps 2–4 parameters are reconfigurable at runtime via **Options** without restarting Home Assistant. When you save Options, the integration reloads automatically.

### Calibration walkthrough

Once installed and running, watch the pergola on a clear day with the **Profile Angle**, **Solar Target**, and **Final Target** sensors graphed in your dashboard.

**To find your `flip_profile_threshold`**: in summer mode, watch the moment a first beam of sun starts to slip between the fully-tilted blades. The value of `sensor.pergola_profile_angle` at that moment is your threshold. Default 80° works for most setups.

**To find your `phase_a_intercept`**: pick any moment in summer phase A where you can visually confirm what closure is "just enough" to block direct rays. Read the profile angle and target. Solve:
```
intercept = (target_pct × flip_threshold - 100 × profile) / (flip_threshold - profile)
```
e.g. if at profile=60° the minimum that blocks rays is 85%, with flip_threshold=85°: intercept ≈ (85·85 − 100·60) / (85−60) = 40%.

**To find your `blade_pitch_ratio`**: measure the centre-to-centre distance between two adjacent blades (pitch) and divide by the blade width. Most products give both in their spec sheet.

**To find your `calibration_offset`**: on a clear morning with default settings, watch whether the pergola is closing too much or too little. Adjust by ±5° at a time. Negative values open more, positive values close more.

### Release process (HACS)

HACS detects new versions only from **GitHub releases**, not plain tags. To ship:

1. Bump `version` in `custom_components/pergola_bioclimatique/manifest.json`.
2. Commit and tag.
3. Create a GitHub release for that tag (`gh release create v1.X.Y …`) — a tag alone is not enough.

### Contributing

Issues and PRs welcome at https://github.com/qelanhari/ha-pergola.

For algorithm / control-loop changes, please add tests in `tests/test_solar.py` (the math module is HA-runtime free and easy to test). For UI / config-flow changes, please keep `strings.json`, `translations/en.json`, and `translations/fr.json` in sync.
