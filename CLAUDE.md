# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Home Assistant custom integration (`pergola_bioclimatique`) that controls bioclimatic pergola slat tilt based on solar position, with cloud detection, humidity blocking, safety locks, and morning calibration. Distributed via HACS. See `README.md` for the user-facing feature description and config-flow parameters.

## Commands

Two flavors of tests, picked by the developer based on what's installed:

```bash
# System pytest — runs everything except the end-to-end flow tests.
# Imports solar.py and config_flow.py via sys.path manipulation (see the
# top of each test file) so no Home Assistant runtime is needed.
pytest                                 # solar + helper + snapshot (~160 tests)

# Full suite (incl. end-to-end install/options flow with mocked HA).
# Needs pytest-homeassistant-custom-component — install in an isolated venv:
python3 -m venv .venv-test
.venv-test/bin/pip install -r requirements_test.txt
.venv-test/bin/pytest                  # ~169 tests including flow walkthroughs
```

Test layout:
- `tests/test_solar.py` — pure math (compute_profile_angle, winter/summer targets, cloud detection).
- `tests/test_config_flow_helpers.py` — helper functions in config_flow.py (`_geometry_defaults`, `_cloud_defaults`, `_geometry_has_non_defaults`, `_cloud_has_non_defaults`); parametrized across cardinal directions. Includes a storage-equivalence proof that the basic flow stores a byte-identical dict to the legacy default install.
- `tests/test_config_flow.py` — install + Options walkthroughs against a mocked Home Assistant. Skipped automatically (via `pytest.importorskip`) when the plugin isn't installed.
- `tests/test_baseline_snapshot.py` — day-in-the-life regression: locks `(profile_angle, winter_target, summer_target)` outputs for a representative summer and winter day. First run bootstraps `tests/snapshots/baseline.json` and skips; rerun validates. `UPDATE_SNAPSHOT=1 pytest …` rewrites the snapshot for intentional algorithm changes.
- `tests/conftest.py` — `default_config` / `minimal_config` / `customized_config` fixtures mirroring the current schema.

There is no build step, lint config, or CI pinned in the repo. The integration is loaded by Home Assistant directly from `custom_components/pergola_bioclimatique/`.

## Release process (HACS)

HACS detects new versions only from **GitHub releases**, not plain tags. To ship:

1. Bump `version` in `custom_components/pergola_bioclimatique/manifest.json`.
2. Commit and tag.
3. Create a GitHub release for that tag (`gh release create ...`) — a tag alone is not enough.

## Architecture

The integration is a single-device integration built around one `DataUpdateCoordinator`:

- **`coordinator.py` (`PergolaCoordinator`)** — the brain. Owns the periodic control loop, persisted state (via `homeassistant.helpers.storage.Store`), state-change subscriptions for sun/PV/humidity/lock entities, morning calibration sequence, safety watchdog, and cloud-state hysteresis. All entities (`sensor`, `binary_sensor`, `select`, `button`) are thin views over `coordinator.data`.
- **`solar.py`** — pure functions: `compute_profile_angle`, `compute_winter_target`, `compute_summer_target`, `compute_pv_threshold`, `panel_cos_aoi`, `is_sunny`, `smooth_pv`, `quantize`, `angle_to_percent`. No Home Assistant imports — this is what the test suite exercises.
- **`config_flow.py`** — 4-step setup wizard (entities → geometry → operation → cloud detection) plus an Options flow that mirrors steps 2–4. Steps 2 and 4 now have a **basic / advanced split**: the basic form shows only the essential field (`face_azimuth` / `pv_max_watts`) plus a `Show advanced settings` toggle. Ticking it transitions to a sub-step exposing every knob. When left unticked, the flow writes every `DEFAULT_*` value silently so the stored entry is byte-identical to a legacy default install. The Options flow auto-opens in the advanced view when any stored field already differs from its default. Updating options triggers `async_reload` of the entry (see `__init__.py::_async_update_listener`).
- **`const.py`** — every `CONF_*` key, `DEFAULT_*` value, and `PLATFORMS` list. New config fields must be added here, in `config_flow.py` (both basic-or-advanced schema and `_geometry_defaults` / `_cloud_defaults` if the field belongs to one of the gated steps), in `coordinator.py`, and in both `strings.json` and `translations/{en,fr}.json`.

### Control loop logic

Each tick (`CONF_UPDATE_INTERVAL`, default 5 min) the coordinator:

1. Reads sun azimuth/elevation, PV/light, humidity, safety-lock states from `hass.states`.
2. Computes a `profile_angle` and a `solar_target` percent via `solar.py` (winter or summer mode).
3. Applies overrides in priority order:
   - **Safety lock** active (rain/temperature/security) — rain holds, temp/security closes.
   - **Not-yet-calibrated** — skip movement, await morning calibration.
   - **Humidity over threshold** — skip movement.
   - **Outside sun exposure window** (`CONF_SUN_AZ_MIN` / `CONF_SUN_AZ_MAX`, defaults `face_azimuth ± 90°`) — building itself shadows the pergola; fall back to `cloudy_target` directly without computing a solar target.
   - **Cloudy state** — fall back to `cloudy_target`; in winter, hold the previously commanded position if higher.
   - **Solar target below `min_useful_percent`** — twilight guard; fall back to `cloudy_target`.
   - Otherwise → use the solar target.
4. Quantizes by `step_size` and applies a `deadband` before issuing `cover.set_cover_tilt_position` (or `open_cover_tilt`/`close_cover_tilt` at the 0%/100% extremes — this preserves mechanical calibration).

State that must survive restarts (last calibration date, cloud hysteresis state, smoothed PV/lux, `last_known_position`) is persisted every cycle via the `Store` — that frequency is intentional, see git history around `pv_smooth` after-restart staleness.

### Solar math (`solar.py`)

- **Winter** — `compute_winter_target` is a straight `raw_angle = profile + offset` → percent, clamped at the bottom by `current_pos` so the position never descends mid-day (implicit hold).
- **Summer phase A** (`profile < flip_profile_threshold`) — **linear ramp** from `(0, phase_a_intercept)` to `(flip_threshold, 100%)`. Theoretical cutoff geometry has the wrong slope for real blades; field observation showed a linear model matches across the whole pre-bascule range. `CONF_PHASE_A_INTERCEPT` (default 40%) is the only tuning knob.
- **Summer phase B** (`profile ≥ flip_profile_threshold`) — **cutoff geometry**: `blade = profile − 90 + arccos(pitch_ratio × sin(profile)) + calibration_offset + summer_blade_offset`. `CONF_SUMMER_BLADE_OFFSET` (default 0°) is phase-B-only and additive on top of `calibration_offset`; lets the user tweak the afternoon side without affecting winter or morning behavior. **Capped at `min(cloudy_target, perpendicular)`**, quantized (the coordinator passes `cloudy_target` in; perpendicular = `90/max_opening_angle` ≈ 67% at 135°): perpendicular blades are the last position that still projects shade — past it the raw geometry keeps opening toward 100%, but that's tracking sun the blades can no longer block. So phase B ramps up to the cap and rests there; `cloudy_target` can only lower the resting point, never push tracking past perpendicular. This is the everyday afternoon end-state; `CONF_SUN_AZ_MAX` is now only the building-self-shadow / model-validity guard (it must stay wide enough that the cap is reached before the azimuth window closes, else the old 50→`cloudy_target` jump returns). Pass `cloudy_target=None` to `compute_summer_target` for the raw uncapped curve (the baseline snapshot does this).
- **Cloud detection** — `is_sunny` OR-combines observable PV and lux votes. Observability gates: `pv_observable_cos` filters PV votes when the panel's `cos(angle_of_incidence)` is too low (blocks false-cloudy when panel is shaded or off-axis); `lux_az_min`/`lux_az_max` filters lux votes outside the azimuth window where the lux sensor sees direct sun. **When neither sensor is observable**, the previous `is_sunny` state is held — important for bridging blind spots like the sun behind the building.
- **PV threshold** — `pv_threshold = max(0, cos(AoI)) × pv_max × pv_sunny_ratio`, computed dynamically from sun position and the configured panel azimuth/tilt.

### Morning calibration

When sun elevation crosses `CONF_MIN_ELEVATION` for the first time each day and the integration is not yet `_pergola_ready`:

1. **Drift-skip optimization**: compare current cover position to the persisted `_last_known_position` (the position last successfully commanded by the integration). If they match within `deadband`, no drift could have happened overnight → mark today as calibrated without moving. Avoids pointless close-and-reopen cycles when yesterday's evening target and today's morning target are both `cloudy_target`.
2. Otherwise → close fully (sends `close_cover_tilt`), wait 45 s, verify position < 5%, mark calibrated.
3. Set `_pergola_ready = True` and `_descent_calibrated = False` (the first descent of the day will re-calibrate through 0%).

### Modes

`select.py` exposes `Hiver` / `Ete` / `Manuel`. Manuel disables the loop entirely; the other two pick which `compute_*_target` runs.

### Persisted state (`Store`)

Saved every cycle (intentionally, see `c966414`):

- `pv_smooth`, `lux_smooth` — exponentially smoothed cloud-sensor readings
- `is_sunny` — current cloud state
- `mode` — current select value
- `last_calibration` — ISO date of last morning calibration
- `pergola_ready` — unlocked after morning calibration
- `descent_calibrated` — flag set after the first descent of the day
- `consecutive_failures` — failed movement count (drives `binary_sensor.movement_problem`)
- `last_known_position` — last position the integration successfully commanded (drives the drift-skip optimization above)

The cloud hysteresis timer (`sunny_changed_at`) is deliberately **not** persisted (see `212f6dd`) so a restart doesn't lock the integration into "cloudy" for 15 min on a clear morning.

## Conventions

- All user-visible strings live in `strings.json` and both `translations/en.json` and `translations/fr.json` — keep all three in sync when adding/renaming options.
- `solar.py` must remain free of `homeassistant` imports so the test suite can import it standalone.
- Prefer adding pure logic to `solar.py` (testable) over `coordinator.py` (requires HA runtime to exercise).
- **Defaults are load-bearing**: the integration is shipped with one supported "preset" — the current `DEFAULT_*` values, tuned by the maintainer's observation of a real pergola. Changing a default is a behavior change that needs strong justification (and probably a version bump). When adding a new config field, pick a default that preserves existing behavior when the new field is absent.
- The config flow's basic/advanced gate is UI sugar only. `CONF_*` keys are the same in basic-saved and advanced-saved entries — `coordinator.py` reads from `config_entry.data` without caring how the user got there. If you add a new geometry/cloud field, also add it to `_geometry_defaults` / `_cloud_defaults` in `config_flow.py` so the basic flow writes a sensible default.
- `CONF_PERGOLA_MODEL` (added in v1.15) is stored in `config_entry.data` but **never read by `coordinator.py`** — it's purely a UI hint so the Options flow can pre-select the user's chosen model. The actual geometry values that drive the algorithm come from `CONF_MAX_OPENING_ANGLE`, `CONF_BLADE_PITCH_RATIO`, etc. — picking a preset just overlays those keys via `get_preset_values(model_id)` during the install/Options flow.
- **Adding a new pergola model preset**: append an entry to `custom_components/pergola_bioclimatique/presets.py` with `display_name`, `brand`, `values` (only `CONF_*` keys from `_GEOMETRY_ADVANCED_FIELDS`), `source` (`"verified"` or `"community"`), `source_url`, and `notes`. Run `pytest tests/test_presets.py` to validate schema and bounds. Don't include `blade_pitch_ratio` unless you have a manufacturer-published value or community-validated measurement — it defaults to 0.92 (typical waterproof louver) otherwise.
