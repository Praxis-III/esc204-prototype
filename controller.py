# controller.py
# ─────────────────────────────────────────────────────────────────────────────
# The brain of the system. Reads all sensors, fetches weather, and decides
# what to do with the valves and heater.
#
# Decision cases implemented:
#   BASE CASES (as specified):
#     Case 1: Sun is out + forecast good → start PVT flow
#     Case 2: PVT at 60°C → fill storage tank
#     Case 3: Supply tank low → emergency refill regardless of temperature
#
#   ADDITIONAL CASES (added for robustness):
#     Case 4: Freeze protection — drain pipes if near 0°C
#     Case 5: Storage tank overtemperature protection
#     Case 6: Heater hysteresis — maintain storage above 50°C minimum
#     Case 7: Night-time mode — close all valves, conserve heat
#     Case 8: Storage full — stop filling even if PVT is hot
#     Case 9: Cloud transient — don't stop flow for brief cloud cover
#     Case 10: Pre-emptive heating — turn heater on early if no sun expected
# ─────────────────────────────────────────────────────────────────────────────

import time
import sensors
import actuators
import weather
from config import (
    TEMP_PVT_READY, TEMP_STORAGE_TARGET, TEMP_STORAGE_MINIMUM,
    TEMP_STORAGE_HEATER_ON, TEMP_STORAGE_HEATER_OFF,
    TEMP_FREEZE_PROTECTION,
    LDR_SUNLIGHT_THRESHOLD, LDR_BRIGHT_SUN_THRESHOLD,
    SUPPLY_TANK_REFILL_THRESHOLD,
    STORAGE_TANK_MAX_VOLUME_L, SUPPLY_TANK_MAX_VOLUME_L,
    WEATHER_FETCH_INTERVAL_S, CONTROL_LOOP_INTERVAL_S,
)

# ── Internal State ─────────────────────────────────────────────────────────────
_last_weather_fetch = 0
_pvt_flow_started_at = None   # timestamp when we opened supply valve
_cloud_transient_start = None # timestamp when we first noticed clouds during flow

# How long we tolerate cloud cover before stopping PVT flow (seconds)
CLOUD_TOLERANCE_S = 600  # 10 minutes of cloud before we give up


# ── Helper: Read Everything ───────────────────────────────────────────────────

def read_all_sensors():
    """
    Reads and returns a unified snapshot of all sensor values.
    Returns a dict. None values mean "sensor not responding."
    """
    storage_temps = sensors.read_storage_temps()
    pvt_temp      = sensors.read_pvt_temp()
    ldr_raw       = sensors.read_ldr_raw()
    storage_vol   = sensors.read_storage_volume_litres()
    storage_frac  = storage_vol / STORAGE_TANK_MAX_VOLUME_L

    # Derived values
    sun_is_out    = ldr_raw >= LDR_SUNLIGHT_THRESHOLD
    strong_sun    = ldr_raw >= LDR_BRIGHT_SUN_THRESHOLD

    # Average storage temperature (ignore None sensors)
    valid_temps = [t for t in storage_temps.values() if t is not None]
    avg_storage_temp = sum(valid_temps) / len(valid_temps) if valid_temps else None

    return {
        'storage_top':    storage_temps['top'],
        'storage_mid':    storage_temps['mid'],
        'storage_bottom': storage_temps['bottom'],
        'avg_storage':    avg_storage_temp,
        'pvt_temp':       pvt_temp,
        'ldr_raw':        ldr_raw,
        'sun_is_out':     sun_is_out,
        'strong_sun':     strong_sun,
        'storage_vol_l':  storage_vol,
        'storage_frac':   storage_frac,
    }


def print_sensor_snapshot(s):
    print(f"  Storage temps  → top:{s['storage_top']}°C  mid:{s['storage_mid']}°C  bot:{s['storage_bottom']}°C  avg:{s['avg_storage']}°C")
    print(f"  PVT temp       → {s['pvt_temp']}°C")
    print(f"  Storage volume → {s['storage_vol_l']}L ({s['storage_frac']*100:.0f}% full)")
    print(f"  Sunlight (LDR) → raw:{s['ldr_raw']}  sun_out:{s['sun_is_out']}  strong:{s['strong_sun']}")
    actuators.print_state()


# ── Main Control Function ─────────────────────────────────────────────────────

def run_control_loop():
    """
    Called repeatedly by main.py on a timer.
    Reads sensors → evaluates all cases → actuates.
    """
    global _last_weather_fetch, _pvt_flow_started_at, _cloud_transient_start

    now = time.time()
    print(f"\n{'='*55}")
    print(f"Control loop running at t={now}")

    # ── 1. Refresh weather forecast if due ────────────────────────────────────
    if now - _last_weather_fetch >= WEATHER_FETCH_INTERVAL_S:
        weather.fetch_forecast()
        _last_weather_fetch = now

    # ── 2. Read all sensors ───────────────────────────────────────────────────
    s = read_all_sensors()
    print_sensor_snapshot(s)

    # ── SAFETY FIRST: Freeze protection (Case 4) ──────────────────────────────
    # If any sensor reads near freezing, drain the PVT pipes immediately.
    # This prevents ice damage regardless of any other logic.
    any_temp = [t for t in [s['storage_top'], s['storage_mid'], s['storage_bottom'], s['pvt_temp']] if t is not None]
    if any_temp and min(any_temp) <= TEMP_FREEZE_PROTECTION:
        print(f"\n[CASE 4] FREEZE PROTECTION — temp near {TEMP_FREEZE_PROTECTION}°C!")
        actuators.open_storage_valve("freeze: drain PVT into storage")
        actuators.close_supply_valve("freeze: stop cold supply")
        # Turn heater on to protect storage water
        actuators.heater_on("freeze: protect storage tank")
        return  # Skip all other logic — safety first

    # ── SAFETY: Overtemperature in storage (Case 5) ───────────────────────────
    # If the top of the storage tank goes way above target (e.g. >80°C),
    # something is wrong — close all valves and heater.
    if s['storage_top'] is not None and s['storage_top'] > 80.0:
        print(f"\n[CASE 5] OVERTEMPERATURE in storage ({s['storage_top']}°C) — halting!")
        actuators.emergency_stop("Storage overtemperature")
        return

    # ── PRIORITY 1: Supply tank refill / minimum demand (Case 3) ──────────────
    # We model supply tank volume by assuming it started full and track what
    # left. For now we use the storage volume indirectly.
    # NOTE: In a real system you would add a pressure sensor to the supply tank.
    # Here we use a placeholder fraction — replace with real supply sensor.
    supply_frac = _estimate_supply_fraction(s)

    if supply_frac < (1.0 - SUPPLY_TANK_REFILL_THRESHOLD):
        # Supply critically low (below refill threshold)
        print(f"\n[CASE 3] Supply tank low ({supply_frac*100:.0f}%) — emergency refill from PVT")

        # Estimate mixing temperature: PVT water (cold or warm) into storage
        # We assume PVT holds roughly 20L (set this to your pipe+panel volume)
        PVT_PIPE_VOLUME_L = 20.0
        pvt_t   = s['pvt_temp']   if s['pvt_temp']   is not None else 15.0
        stor_t  = s['avg_storage'] if s['avg_storage'] is not None else 60.0
        stor_vol = s['storage_vol_l']

        mixed_temp = sensors.estimate_mixed_temp(
            stor_t, pvt_t,
            stor_vol, PVT_PIPE_VOLUME_L
        )
        print(f"  Estimated mixed storage temp if refilled: {mixed_temp:.1f}°C")

        # Open both valves to push water through
        actuators.open_supply_valve("Case 3: emergency refill")
        actuators.open_storage_valve("Case 3: emergency refill")

        # If mixing will drop below minimum, pre-emptively turn on heater
        if mixed_temp is not None and mixed_temp < TEMP_STORAGE_MINIMUM:
            print(f"  Mixed temp {mixed_temp:.1f}°C < minimum {TEMP_STORAGE_MINIMUM}°C — turning heater ON")
            actuators.heater_on("Case 3: temp will drop below minimum after refill")
        return  # Don't evaluate lower-priority cases this cycle

    # ── PRIORITY 2: Fill storage from hot PVT (Case 2) ────────────────────────
    pvt_ready = (s['pvt_temp'] is not None and s['pvt_temp'] >= TEMP_PVT_READY)
    storage_full = s['storage_frac'] >= 0.99

    if pvt_ready and not storage_full:
        print(f"\n[CASE 2] PVT hot ({s['pvt_temp']}°C ≥ {TEMP_PVT_READY}°C) — filling storage")

        if storage_full:
            # Case 8: Storage full — don't overflow it
            print(f"  [CASE 8] Storage full — closing storage valve")
            actuators.close_storage_valve("Case 8: storage full")
            actuators.close_supply_valve("Case 8: storage full, stopping PVT flow")
        else:
            actuators.open_supply_valve("Case 2: PVT hot, continue flow")
            actuators.open_storage_valve("Case 2: PVT hot, filling storage")
            _pvt_flow_started_at = _pvt_flow_started_at or now

    # ── PRIORITY 3: Start PVT flow when sun is out (Case 1) ───────────────────
    elif not pvt_ready and not actuators.supply_valve_is_open():
        # PVT is not yet hot — should we start the flow?
        sun_out         = s['sun_is_out']
        sun_forecast_ok = weather.sun_will_last_long_enough()

        print(f"\n[CASE 1] Considering starting PVT flow: sun_out={sun_out}, forecast_ok={sun_forecast_ok}")

        if sun_out and (sun_forecast_ok is True or sun_forecast_ok is None):
            # Sun is out now AND forecast looks good (or forecast unavailable — err on sunny side)
            print(f"  Sun confirmed — opening supply valve to start PVT heating")
            actuators.open_supply_valve("Case 1: sun is out, forecast good")
            actuators.close_storage_valve("Case 1: PVT not hot yet, keep storage closed")
            _pvt_flow_started_at = now
        else:
            # No sun or forecast bad — make sure valves are closed
            actuators.close_supply_valve("Case 1: no sun or poor forecast")
            actuators.close_storage_valve("Case 1: no sun or poor forecast")
            _pvt_flow_started_at = None

    # ── Case 9: Cloud transient during active PVT flow ────────────────────────
    # If sun disappears briefly, don't immediately stop — give it CLOUD_TOLERANCE_S
    elif actuators.supply_valve_is_open() and not s['sun_is_out'] and not pvt_ready:
        if _cloud_transient_start is None:
            _cloud_transient_start = now
            print(f"\n[CASE 9] Cloud transient — watching (tolerance={CLOUD_TOLERANCE_S}s)")
        elif now - _cloud_transient_start > CLOUD_TOLERANCE_S:
            print(f"\n[CASE 9] Cloud persisted >{CLOUD_TOLERANCE_S}s — stopping PVT flow")
            actuators.close_supply_valve("Case 9: prolonged cloud cover")
            actuators.close_storage_valve("Case 9: prolonged cloud cover")
            _pvt_flow_started_at  = None
            _cloud_transient_start = None
    else:
        _cloud_transient_start = None  # Reset transient timer if sun returned

    # ── HEATER CONTROL ────────────────────────────────────────────────────────

    avg = s['avg_storage']

    if avg is not None:

        # Case 6: Heater hysteresis — maintain storage above minimum
        if avg <= TEMP_STORAGE_HEATER_ON and not actuators.heater_is_on():
            print(f"\n[CASE 6] Storage avg {avg:.1f}°C ≤ heater-on threshold {TEMP_STORAGE_HEATER_ON}°C — heater ON")
            actuators.heater_on("Case 6: storage temp below heater-on threshold")

        elif avg >= TEMP_STORAGE_HEATER_OFF and actuators.heater_is_on():
            print(f"\n[CASE 6] Storage avg {avg:.1f}°C ≥ target {TEMP_STORAGE_HEATER_OFF}°C — heater OFF")
            actuators.heater_off("Case 6: storage reached target temp")

        # Case 10: Pre-emptive heating — if no sunshine expected in next 12h,
        # use off-peak grid to top up storage before it drops below minimum
        sunshine_hours = weather.get_next_sunshine_hours()
        if sunshine_hours == 0 and avg < TEMP_STORAGE_TARGET and not actuators.heater_is_on():
            print(f"\n[CASE 10] No sun expected for 12h + storage at {avg:.1f}°C — pre-heating")
            actuators.heater_on("Case 10: no solar expected, pre-heating storage")

    # ── Case 7: Night-time / low-light passive mode ───────────────────────────
    # If LDR says it's dark and no flow is happening, ensure valves are closed
    # to prevent convective cooling of storage through the pipe circuit.
    if not s['sun_is_out'] and not actuators.supply_valve_is_open():
        if actuators.storage_valve_is_open():
            print(f"\n[CASE 7] Night/dark mode — closing storage valve to prevent heat loss")
            actuators.close_storage_valve("Case 7: night mode, prevent convective loss")

    print(f"\nControl loop complete.")


# ── Placeholder: supply tank volume estimate ───────────────────────────────────

def _estimate_supply_fraction(s):
    """
    Placeholder for supply tank volume.
    In a full implementation, you would read a pressure sensor on the supply tank.
    For now, returns a fixed 1.0 (full) so Case 3 never triggers by default.
    Replace this with your real supply sensor reading.
    """
    # TODO: Replace with: return sensors.read_supply_volume_litres() / SUPPLY_TANK_MAX_VOLUME_L
    return 1.0
