# controller.py
# ─────────────────────────────────────────────────────────────────────────────
# The brain of the system. Reads all sensors, fetches weather, and decides
# what to do with the valve and LED.
#
# Physical setup:
#   - PVT model tank:   one thermistor (GPIO28), manually refilled
#   - Storage tank:     one thermistor (GPIO27), one pressure sensor
#   - One stepper motor valve between PVT tank and storage tank
#   - One LED standing in for a heater
#   - One photoresistor for sunlight detection
#
# Valve open decision (Option B — combined):
#   The photoresistor + weather forecast determine WHETHER conditions are
#   favourable for flow. The PVT thermistor confirms the water is ACTUALLY
#   hot enough. Both conditions must be true before the valve opens.
#
# Decision cases:
#   Case 1:  Sun out + good forecast + PVT ≥ 60°C → open valve
#   Case 2:  Storage full → close valve
#   Case 3:  Storage volume low → print alert, no hardware action
#   Case 4:  Freeze protection → close valve, LED on
#   Case 5:  Overtemperature in storage → emergency stop
#   Case 6:  LED hysteresis → on at 52°C, off at 60°C
#   Case 7:  Night mode → close valve to prevent heat loss
#   Case 8:  Cloud transient → tolerate 10 min before closing valve
#   Case 9:  Pre-emptive LED → no sun forecast + storage below target
# ─────────────────────────────────────────────────────────────────────────────

import time
import sensors
import actuators
import weather
import custom_data
from config import (
    TEMP_PVT_READY,
    TEMP_STORAGE_TARGET,
    TEMP_STORAGE_LED_ON, TEMP_STORAGE_LED_OFF,
    TEMP_FREEZE_PROTECTION,
    LDR_SUNLIGHT_LUX,
    STORAGE_REFILL_THRESHOLD,
    STORAGE_TANK_MAX_VOLUME_L,
    TESTING_MODE,
)

# ── Internal state ─────────────────────────────────────────────────────────────
_valve_opened_at       = None
_cloud_transient_start = None

CLOUD_TOLERANCE_S = 600   # 10 minutes


# ── Sensor snapshot ────────────────────────────────────────────────────────────

def read_all_sensors():
    """
    Reads and returns a unified snapshot of all sensor values.
    None values mean the sensor returned an implausible reading.
    """
    storage_temp = sensors.read_storage_temp_c()
    pvt_temp     = sensors.read_pvt_temp_c()
    lux          = sensors.read_lux()
    storage_vol  = sensors.read_storage_volume_litres()
    storage_frac = sensors.read_storage_fill_fraction()
    sun_out      = lux >= LDR_SUNLIGHT_LUX if lux is not None else False
    pvt_ready    = pvt_temp is not None and pvt_temp >= TEMP_PVT_READY

    return {
        'storage_temp':  storage_temp,
        'pvt_temp':      pvt_temp,
        'pvt_ready':     pvt_ready,
        'lux':           lux,
        'sun_is_out':    sun_out,
        'storage_vol_l': storage_vol,
        'storage_frac':  storage_frac,
    }


def read_custom_data():
    """Returns latest custom test snapshot, falling back to physical sensors."""
    snapshot = custom_data.get_latest_snapshot()
    if snapshot is None:
        print("  No custom data received yet; falling back to physical sensors.")
        return read_all_sensors()
    return snapshot

def print_sensor_snapshot(s):
    print(f"  Storage temp   → {s['storage_temp']}°C")
    print(f"  PVT temp       → {s['pvt_temp']}°C  (ready:{s['pvt_ready']})")
    print(f"  Light level    → {s['lux']} lux  (sun_out:{s['sun_is_out']})")
    print(f"  Storage volume → {s['storage_vol_l']}L ({s['storage_frac']*100:.0f}% full)")
    actuators.print_state()


# ── Main control function ──────────────────────────────────────────────────────

def run_control_loop():
    """
    Called repeatedly by main.py on a timer.
    Reads sensors → evaluates all cases in priority order → actuates.
    """
    global _valve_opened_at, _cloud_transient_start

    now = time.time()
    print(f"\n{'='*55}")
    print(f"Control loop running at t={now}")

    # ── Pull in any weather packets that arrived over USB serial ──────────────
    weather_updates = weather.poll_serial(max_lines=10)
    if weather_updates > 0:
        print(f"  Applied {weather_updates} weather update(s) from serial.")

    # ── Read all sensors ──────────────────────────────────────────────────────
    s = read_all_sensors() if not TESTING_MODE else read_custom_data()
    if TESTING_MODE:
        print("  Sensor source   -> custom test data")
    print_sensor_snapshot(s)

    storage_temp = s['storage_temp']

    # ── CASE 4: Freeze protection ─────────────────────────────────────────────
    # Check both sensors — if either reads near freezing, close valve immediately.
    temps_to_check = [t for t in [storage_temp, s['pvt_temp']] if t is not None]
    if temps_to_check and min(temps_to_check) <= TEMP_FREEZE_PROTECTION:
        frozen = min(temps_to_check)
        print(f"\n[CASE 4] FREEZE PROTECTION — sensor reading {frozen}°C ≤ {TEMP_FREEZE_PROTECTION}°C")
        actuators.close_valve("Case 4: freeze protection")
        actuators.led_on("Case 4: freeze — protecting storage water")
        return

    # ── CASE 5: Overtemperature ───────────────────────────────────────────────
    if storage_temp is not None and storage_temp > 80.0:
        print(f"\n[CASE 5] OVERTEMPERATURE — storage at {storage_temp}°C")
        actuators.emergency_stop("Case 5: overtemperature")
        return

    # ── CASE 3: Storage volume low — print alert ──────────────────────────────
    if s['storage_frac'] < (1.0 - STORAGE_REFILL_THRESHOLD):
        print(f"\n[CASE 3] ⚠️  LOW WATER ALERT: Storage at {s['storage_frac']*100:.0f}%.")
        print(f"         There is a sudden drop in water level — storage tank needs to be refilled manually.")

    # ── CASE 2: Storage full → close valve ────────────────────────────────────
    if s['storage_frac'] >= 0.99:
        print(f"\n[CASE 2] Storage full — closing valve")
        actuators.close_valve("Case 2: storage tank full")
        _valve_opened_at = None

    # ── CASE 1: Combined condition — sun + forecast + PVT hot → open valve ────
    # Option B: photoresistor and forecast determine whether conditions are
    # favourable; PVT thermistor confirms water is actually hot enough.
    # ALL THREE must be satisfied before the valve opens.
    elif not actuators.valve_is_open():
        sun_out = s['sun_is_out']
        pvt_ready = s['pvt_ready']

        if TESTING_MODE and s.get('sun_forecast_ok') is not None:
            sun_forecast_ok = s['sun_forecast_ok']
        else:
            sun_forecast_ok = weather.sun_will_last_long_enough()

        print(f"\n[CASE 1] Valve open check:")
        print(f"         sun_out={sun_out}  pvt_ready={pvt_ready} ({s['pvt_temp']}°C)  forecast_ok={sun_forecast_ok}")

        if sun_out and pvt_ready and (sun_forecast_ok is True or sun_forecast_ok is None):
            print(f"  All conditions met — opening valve")
            actuators.open_valve("Case 1: sun out, PVT hot, forecast good")
            _valve_opened_at       = now
            _cloud_transient_start = None

        elif not pvt_ready and sun_out:
            # Sun is out but PVT not hot yet — waiting for water to heat up
            print(f"  Sun out but PVT only {s['pvt_temp']}°C — waiting for PVT to reach {TEMP_PVT_READY}°C")

        else:
            actuators.close_valve("Case 1: conditions not met")
            _valve_opened_at = None

    # ── CASE 8: Cloud transient during active flow ────────────────────────────
    # If sun disappears while valve is open, tolerate CLOUD_TOLERANCE_S before
    # closing. Note: valve stays open as long as PVT is still hot even if
    # sun disappears briefly — water already heated is worth transferring.
    elif actuators.valve_is_open() and not s['sun_is_out']:
        if _cloud_transient_start is None:
            _cloud_transient_start = now
            print(f"\n[CASE 8] Cloud cover detected — watching for {CLOUD_TOLERANCE_S}s")
        elif now - _cloud_transient_start > CLOUD_TOLERANCE_S:
            print(f"\n[CASE 8] Cloud persisted >{CLOUD_TOLERANCE_S}s — closing valve")
            actuators.close_valve("Case 8: prolonged cloud cover")
            _valve_opened_at       = None
            _cloud_transient_start = None
    else:
        _cloud_transient_start = None

    # ── CASE 7: Night / dark mode ─────────────────────────────────────────────
    if not s['sun_is_out'] and not actuators.valve_is_open():
        if actuators.valve_is_open():
            print(f"\n[CASE 7] Dark/night — closing valve to prevent heat loss")
            actuators.close_valve("Case 7: night mode")

    # ── LED CONTROL ───────────────────────────────────────────────────────────

    if storage_temp is not None:

        # Case 6: Hysteresis — LED on at 52°C, off at 60°C
        if storage_temp <= TEMP_STORAGE_LED_ON and not actuators.led_is_on():
            print(f"\n[CASE 6] Storage at {storage_temp}°C ≤ {TEMP_STORAGE_LED_ON}°C — LED ON")
            actuators.led_on("Case 6: storage below LED-on threshold")

        elif storage_temp >= TEMP_STORAGE_LED_OFF and actuators.led_is_on():
            print(f"\n[CASE 6] Storage at {storage_temp}°C ≥ {TEMP_STORAGE_LED_OFF}°C — LED OFF")
            actuators.led_off("Case 6: storage reached target temp")

        # Case 9: Pre-emptive LED — no sun expected + storage below target
        if TESTING_MODE and s.get('sun_forecast_ok') is not None:
            sunshine_hours = 1 if s['sun_forecast_ok'] else 0
        else:
            sunshine_hours = weather.get_next_sunshine_hours()
        if sunshine_hours == 0 and storage_temp < TEMP_STORAGE_TARGET and not actuators.led_is_on():
            print(f"\n[CASE 9] No sun expected for 12h + storage at {storage_temp}°C — LED ON (pre-emptive)")
            actuators.led_on("Case 9: no solar expected, pre-emptive heating signal")

    print(f"\nControl loop complete.")