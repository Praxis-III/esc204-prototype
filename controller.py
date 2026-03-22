# controller.py
# ─────────────────────────────────────────────────────────────────────────────
# The brain of the system. Reads all sensors, fetches weather, and decides
# what to do with the valve and LED.
#
# Physical setup:
#   - PVT model tank: hot water, manually refilled — no sensors or code needed
#   - Storage tank: one thermistor, one pressure sensor
#   - One stepper motor valve between PVT tank and storage tank
#   - One LED standing in for a heater
#   - One photoresistor for sunlight detection
#
# Decision cases:
#   Case 1:  Sun is out + forecast good → open valve, start flow into storage
#   Case 2:  Storage full → close valve, stop filling
#   Case 3:  Storage volume drops below threshold → print low-water alert
#   Case 4:  Freeze protection → close valve immediately
#   Case 5:  Overtemperature in storage → close valve, LED off
#   Case 6:  LED hysteresis → on at 52°C, off at 60°C
#   Case 7:  Night mode → close valve to prevent heat loss
#   Case 8:  Cloud transient → tolerate 10 min cloud before closing valve
#   Case 9:  Pre-emptive LED → no sun forecast + storage below target
# ─────────────────────────────────────────────────────────────────────────────

import time
import sensors
import actuators
import weather
from config import (
    TEMP_PVT_READY, TEMP_STORAGE_TARGET,
    TEMP_STORAGE_LED_ON, TEMP_STORAGE_LED_OFF,
    TEMP_FREEZE_PROTECTION,
    LDR_SUNLIGHT_LUX,
    STORAGE_REFILL_THRESHOLD,
    STORAGE_TANK_MAX_VOLUME_L,
    WEATHER_FETCH_INTERVAL_S,
)

# ── Internal state ─────────────────────────────────────────────────────────────
_last_weather_fetch    = 0
_valve_opened_at       = None   # Timestamp when valve was opened
_cloud_transient_start = None   # Timestamp when cloud cover was first noticed

# How long to tolerate cloud cover before closing valve (seconds)
CLOUD_TOLERANCE_S = 600   # 10 minutes


# ── Sensor snapshot ────────────────────────────────────────────────────────────

def read_all_sensors():
    """
    Reads and returns a unified snapshot of all sensor values.
    None values mean the sensor returned an implausible reading.
    """
    temp         = sensors.read_temp_c()
    lux          = sensors.read_lux()
    storage_vol  = sensors.read_storage_volume_litres()
    storage_frac = sensors.read_storage_fill_fraction()
    sun_out      = lux >= LDR_SUNLIGHT_LUX if lux is not None else False

    return {
        'temp':         temp,
        'lux':          lux,
        'sun_is_out':   sun_out,
        'storage_vol_l': storage_vol,
        'storage_frac':  storage_frac,
    }

def print_sensor_snapshot(s):
    print(f"  Storage temp   → {s['temp']}°C")
    print(f"  Light level    → {s['lux']} lux  (sun_out:{s['sun_is_out']})")
    print(f"  Storage volume → {s['storage_vol_l']}L ({s['storage_frac']*100:.0f}% full)")
    actuators.print_state()


# ── Main control function ──────────────────────────────────────────────────────

def run_control_loop():
    """
    Called repeatedly by main.py on a timer.
    Reads sensors → evaluates all cases in priority order → actuates.
    """
    global _last_weather_fetch, _valve_opened_at, _cloud_transient_start

    now = time.time()
    print(f"\n{'='*55}")
    print(f"Control loop running at t={now}")

    # ── Refresh weather forecast if due ───────────────────────────────────────
    if now - _last_weather_fetch >= WEATHER_FETCH_INTERVAL_S:
        weather.fetch_forecast()
        _last_weather_fetch = now

    # ── Read all sensors ──────────────────────────────────────────────────────
    s = read_all_sensors()
    print_sensor_snapshot(s)

    temp = s['temp']

    # ── CASE 4: Freeze protection ─────────────────────────────────────────────
    # Highest priority — if temperature is near freezing, close the valve
    # immediately to stop cold water from circulating.
    if temp is not None and temp <= TEMP_FREEZE_PROTECTION:
        print(f"\n[CASE 4] FREEZE PROTECTION — temp {temp}°C ≤ {TEMP_FREEZE_PROTECTION}°C")
        actuators.close_valve("Case 4: freeze protection")
        actuators.led_on("Case 4: freeze — protecting storage water with heat")
        return

    # ── CASE 5: Overtemperature ───────────────────────────────────────────────
    # If storage exceeds a safe ceiling something is wrong — stop everything.
    if temp is not None and temp > 80.0:
        print(f"\n[CASE 5] OVERTEMPERATURE — storage at {temp}°C")
        actuators.emergency_stop("Case 5: overtemperature")
        return

    # ── CASE 3: Storage volume low — print alert ──────────────────────────────
    # No hardware action is taken. Prints a message so the team knows to
    # manually refill. The rest of the loop continues normally.
    if s['storage_frac'] < (1.0 - STORAGE_REFILL_THRESHOLD):
        print(f"\n[CASE 3] ⚠️  LOW WATER ALERT: Storage at {s['storage_frac']*100:.0f}%.")
        print(f"         There is a sudden drop in water level — storage tank needs to be refilled manually.")

    # ── CASE 2: Storage full → close valve ───────────────────────────────────
    if s['storage_frac'] >= 0.99:
        print(f"\n[CASE 2] Storage full — closing valve")
        actuators.close_valve("Case 2: storage tank full")
        _valve_opened_at = None
        # Don't return — still need to evaluate LED cases below

    # ── CASE 1: Sun out + good forecast → open valve ──────────────────────────
    elif not actuators.valve_is_open():
        sun_out         = s['sun_is_out']
        sun_forecast_ok = weather.sun_will_last_long_enough()

        print(f"\n[CASE 1] Considering opening valve: sun_out={sun_out}, forecast_ok={sun_forecast_ok}")

        if sun_out and (sun_forecast_ok is True or sun_forecast_ok is None):
            print(f"  Sun confirmed — opening valve to fill storage from PVT tank")
            actuators.open_valve("Case 1: sun out, forecast good")
            _valve_opened_at       = now
            _cloud_transient_start = None
        else:
            actuators.close_valve("Case 1: no sun or poor forecast")
            _valve_opened_at = None

    # ── CASE 8: Cloud transient during active flow ────────────────────────────
    # If sun disappears while valve is open, give it CLOUD_TOLERANCE_S before
    # closing. Brief cloud cover should not interrupt an active fill cycle.
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
        # Sun returned — reset cloud transient timer
        _cloud_transient_start = None

    # ── CASE 7: Night / dark mode ─────────────────────────────────────────────
    # If it's dark and no flow is active, ensure valve is closed to prevent
    # convective cooling of stored water back through the cold pipe circuit.
    if not s['sun_is_out'] and not actuators.valve_is_open():
        if actuators.valve_is_open():
            print(f"\n[CASE 7] Dark/night — closing valve to prevent heat loss")
            actuators.close_valve("Case 7: night mode")

    # ── LED CONTROL ───────────────────────────────────────────────────────────

    if temp is not None:

        # Case 6: Hysteresis band — LED on at 52°C, off at 60°C
        if temp <= TEMP_STORAGE_LED_ON and not actuators.led_is_on():
            print(f"\n[CASE 6] Storage at {temp}°C ≤ {TEMP_STORAGE_LED_ON}°C — LED ON (would heat water)")
            actuators.led_on("Case 6: storage below LED-on threshold")

        elif temp >= TEMP_STORAGE_LED_OFF and actuators.led_is_on():
            print(f"\n[CASE 6] Storage at {temp}°C ≥ {TEMP_STORAGE_LED_OFF}°C — LED OFF")
            actuators.led_off("Case 6: storage reached target temp")

        # Case 9: Pre-emptive LED — no sun expected + storage below target
        sunshine_hours = weather.get_next_sunshine_hours()
        if sunshine_hours == 0 and temp < TEMP_STORAGE_TARGET and not actuators.led_is_on():
            print(f"\n[CASE 9] No sun expected for 12h + storage at {temp}°C — LED ON (pre-emptive)")
            actuators.led_on("Case 9: no solar expected, pre-emptive heating signal")

    print(f"\nControl loop complete.")
