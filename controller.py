# controller.py
# ─────────────────────────────────────────────────────────────────────────────
# The brain of the system. Reads all sensors and implements the control truth
# table to decide pump and LED (electric heater model) state.
#
# ── Truth table inputs ────────────────────────────────────────────────────────
#   S  Sun available     — current lux >= LDR_SUNLIGHT_LUX (photoresistor)
#   H  Forecast good     — WiFi forecast for next 20-30 min; falls back to
#                          LDR trend if WiFi unavailable or stale (>24h)
#   T  Tank temp low     — storage temp < TEMP_STORAGE_TARGET (60°C)
#   P  PVT ready         — PVT temp >= TEMP_PVT_READY (60°C)
#   W  Tank critically   — storage volume <= 20% of max capacity
#      low
#
# ── Truth table outputs ───────────────────────────────────────────────────────
#   Pump  — 1 = pump running (water flowing PVT → storage), 0 = pump off
#   Heat  — 1 = LED on (models electric heater active),    0 = LED off
#
# ── Tank zone definitions ─────────────────────────────────────────────────────
#   FULL    storage_frac >= 0.99  (≥99%)
#   NORMAL  0.20 < storage_frac < 0.99  (20–99%) — W=0 but not full
#   CRITICAL storage_frac <= 0.20       — W=1
#
# When W=0 and tank is FULL    → use the table output directly
# When W=0 and tank is NORMAL  → use the bracketed annotation in the table
#                                 (usually pump=1 if PVT/sun conditions allow)
# When W=1 (CRITICAL)          → always follow the table's critical-low row
#
# ── Safety overrides (highest priority, checked before truth table) ───────────
#   Freeze protection   either sensor <= 4°C  → pump off, LED on
#   Overtemperature     storage temp  > 80°C  → emergency stop (all off)
#
# ── Demand detection ──────────────────────────────────────────────────────────
#   A rolling volume buffer (PRESSURE_DEMAND_WINDOW_S seconds) detects active
#   water consumption. Used in rows 01001 and 01101 to decide whether to wait
#   for solar or heat immediately.
#
# ── NOTE on volume polling rate ───────────────────────────────────────────────
#   The truth table was designed with the assumption that volume state (W) can
#   change rapidly (someone consuming water). Ideally the HX711 would be polled
#   every ~1s independently of the slower sensor reads. The current architecture
#   reads everything at CONTROL_LOOP_INTERVAL_S (5s). A future iteration should
#   split volume into a fast inner loop and keep temp/weather at the slow rate.
#
# TESTING_MODE = True:
#   All sensor data comes from custom_data serial packets (custom_data_server.py)
#   If no packet has arrived yet the loop waits rather than touching hardware.
# ─────────────────────────────────────────────────────────────────────────────

import time
import sensors
import actuators
import weather
import custom_data
import ldr_trend
from config import (
    TEMP_PVT_READY,
    TEMP_PVT_SOFT,
    TEMP_STORAGE_TARGET,
    TEMP_STORAGE_LED_ON,
    TEMP_STORAGE_LED_OFF,
    TEMP_FREEZE_PROTECTION,
    LDR_SUNLIGHT_LUX,
    LDR_FORECAST_STALE_S,
    STORAGE_TANK_MAX_VOLUME_L,
    PRESSURE_DEMAND_DEADBAND_L,
    PRESSURE_DEMAND_WINDOW_S,
    TESTING_MODE,
    CONTROL_LOOP_INTERVAL_S,
)

# ── Internal state ────────────────────────────────────────────────────────────

# Rolling volume buffer for demand detection: list of (timestamp, volume_L)
_volume_history = []


# ── Volume demand detection ───────────────────────────────────────────────────

def _record_volume(vol_l):
    """Appends current volume to the rolling buffer and prunes old entries."""
    now = time.time()
    _volume_history.append((now, vol_l))
    cutoff = now - PRESSURE_DEMAND_WINDOW_S
    while _volume_history and _volume_history[0][0] < cutoff:
        _volume_history.pop(0)

def _demand_detected(current_vol_l):
    """
    Returns True if the storage tank volume has dropped by more than
    PRESSURE_DEMAND_DEADBAND_L over the demand window — indicating active
    water consumption rather than a stable low-water situation.
    If the buffer is too short to tell, returns False (assume no demand).
    """
    if len(_volume_history) < 2:
        return False
    oldest_vol = _volume_history[0][1]
    drop = oldest_vol - current_vol_l
    detected = drop > PRESSURE_DEMAND_DEADBAND_L
    if detected:
        print(f"  [DEMAND] Drop detected: {oldest_vol:.3f}L → {current_vol_l:.3f}L "
              f"(drop={drop:.3f}L > deadband={PRESSURE_DEMAND_DEADBAND_L}L)")
    return detected


# ── Forecast resolution ───────────────────────────────────────────────────────

def _resolve_forecast(s):
    """
    Returns the best available solar forecast for the next ~20-30 minutes.

    Priority:
      1. Custom data packet forecast (testing mode only)
      2. WiFi weather forecast — if fresh (< LDR_FORECAST_STALE_S old)
      3. LDR trend forecast    — if WiFi is unavailable or stale
      4. None                  — not enough information (caller treats as unknown)
    """
    # 1. Testing mode: use forecast from custom data packet if present
    if TESTING_MODE and s.get('sun_forecast_ok') is not None:
        print(f"  [FORECAST] Source: custom data packet → {s['sun_forecast_ok']}")
        return s['sun_forecast_ok']

    # 2. WiFi forecast — check staleness
    fetched_at  = weather._cache.get('fetched_at', 0)
    age_s       = time.time() - fetched_at
    wifi_fresh  = (fetched_at > 0) and (age_s < LDR_FORECAST_STALE_S)

    if wifi_fresh:
        # Use a short window (1 hour covers the next 20-30 min adequately
        # given Open-Meteo's hourly resolution)
        result = weather.sun_will_last_long_enough(hours_needed=1)
        print(f"  [FORECAST] Source: WiFi (age={age_s:.0f}s) → {result}")
        return result

    # 3. WiFi stale or absent — fall back to LDR trend
    ldr_result = ldr_trend.forecast_ok()
    if fetched_at > 0:
        print(f"  [FORECAST] WiFi stale ({age_s:.0f}s > {LDR_FORECAST_STALE_S}s) "
              f"— using LDR trend → {ldr_result}")
    else:
        print(f"  [FORECAST] No WiFi data — using LDR trend → {ldr_result}")
    return ldr_result


# ── Sensor snapshot ───────────────────────────────────────────────────────────

def _read_sensors():
    """
    Returns a unified sensor snapshot.
    In TESTING_MODE returns the latest custom data packet or None if not yet
    received (caller must handle None — do not fall back to hardware).
    """
    if TESTING_MODE:
        return custom_data.get_latest_snapshot()

    storage_temp = sensors.read_storage_temp_c()
    pvt_temp     = sensors.read_pvt_temp_c()
    lux          = sensors.read_lux()
    storage_vol  = sensors.read_storage_volume_litres()
    storage_frac = sensors.read_storage_fill_fraction()

    return {
        'storage_temp':    storage_temp,
        'pvt_temp':        pvt_temp,
        'pvt_ready':       pvt_temp is not None and pvt_temp >= TEMP_PVT_READY,
        'lux':             lux,
        'sun_is_out':      lux is not None and lux >= LDR_SUNLIGHT_LUX,
        'storage_vol_l':   storage_vol,
        'storage_frac':    storage_frac,
        'sun_forecast_ok': None,   # Filled by _resolve_forecast()
    }


def _print_snapshot(s, S, H, T, P, W, zone):
    print(f"  Storage temp   → {s['storage_temp']}°C")
    print(f"  PVT temp       → {s['pvt_temp']}°C  (ready:{s['pvt_ready']})")
    print(f"  Light level    → {s['lux']} lux")
    print(f"  Storage volume → {s['storage_vol_l']}L ({s['storage_frac']*100:.0f}%)")
    print(f"  Truth table    → S={int(S)} H={int(H)} T={int(T)} P={int(P)} W={int(W)}  zone={zone}")
    actuators.print_state()


# ── LED (heater model) control ────────────────────────────────────────────────

def _apply_led(heat_on, storage_temp, reason=""):
    """
    Applies LED state with hysteresis guard.

    Hysteresis applies only to turning the LED OFF — once the truth table
    requests heating, the LED turns on at any temperature below LED_OFF (60°C).
    It only turns off when storage reaches LED_OFF. This prevents the dead-band
    (LED_ON=52°C to LED_OFF=60°C) from blocking a legitimate heat request.

    heat=1 → LED on  if temp < LED_OFF  (heater needed, not yet at target)
             LED off if temp >= LED_OFF  (already at target, no heating needed)
    heat=0 → LED off if temp >= LED_OFF  (at target)
             LED on  if temp <= LED_ON   (safety floor: temp too low regardless)
             else    leave current state (in dead-band, no table heat request)
    """
    if heat_on:
        if storage_temp is not None and storage_temp >= TEMP_STORAGE_LED_OFF:
            actuators.led_off("Hysteresis: storage at target despite heat request")
        else:
            # Turn on for any temp below LED_OFF — dead-band does not block heat=1
            actuators.led_on(reason)
    else:
        if storage_temp is not None and storage_temp >= TEMP_STORAGE_LED_OFF:
            actuators.led_off(reason)
        elif storage_temp is not None and storage_temp <= TEMP_STORAGE_LED_ON:
            # Safety floor: temp too low — turn on even without table heat request
            actuators.led_on("Safety: storage below LED_ON threshold")
        # Between LED_ON and LED_OFF with heat=0: leave current state


# ── Truth table implementation ────────────────────────────────────────────────

def _apply_truth_table(S, H, T, P, W, zone, s):
    """
    Implements the full 5-input truth table.
    S, H, T, P, W are booleans matching the table definition.
    zone is 'FULL', 'NORMAL', or 'CRITICAL'.

    Returns (pump_on: bool, heat_on: bool, reason: str)

    Table rows are grouped by S,H combination for readability.
    For W=0 rows the output column is the FULL tank output.
    The NORMAL zone override is applied inside each row where annotated.
    """
    pvt_temp     = s.get('pvt_temp')
    storage_temp = s.get('storage_temp')

    # Convenience: soft PVT check used in several rows
    pvt_soft_ok = pvt_temp is not None and pvt_temp >= TEMP_PVT_SOFT

    # ── S=0 H=0 ──────────────────────────────────────────────────────────────
    if not S and not H:
        # 00000 → 00
        if not T and not P and not W:
            return False, False, "00000: no sun, bad forecast, tank ok, PVT cold, tank full"

        # 00001 → 00
        if not T and not P and W:
            return False, False, "00001: no sun, bad forecast, tank ok, PVT cold, critical low"

        # 00010 → 00
        if not T and P and not W:
            if zone == 'NORMAL':
                return False, False, "00010-NORMAL: energy save, wait for better conditions"
            return False, False, "00010: energy save"

        # 00011 → 10  PVT ready, tank critical, no solar — pump without heating
        if not T and P and W:
            return True, False, "00011: PVT ready, tank critical — pump"

        # 00100 → 01  energy save, tank temp low but no solar path available
        if T and not P and not W:
            return False, True, "00100: energy save — tank low but no solar and PVT cold"

        # 00101 → 11  tank critically low, temp low, no solar at all — pump+heat
        if T and not P and W:
            return True, True, "00101: critical low + temp low + no solar — pump and heat"

        # 00110 → 10 (FULL: 10, NORMAL: 10 — pump since PVT has water, tank needs fill)
        if T and P and not W:
            if zone == 'NORMAL':
                return True, False, "00110-NORMAL: PVT ready, tank low temp, pump"
            return True, False, "00110: PVT ready, tank temp low — pump"

        # 00111 → 10  normal pumping condition
        if T and P and W:
            return True, False, "00111: normal pump condition"

    # ── S=0 H=1 ──────────────────────────────────────────────────────────────
    elif not S and H:
        # 01000 → 00
        if not T and not P and not W:
            return False, False, "01000: no sun now, forecast good, tank fine"

        # 01001 → 00 until demand detected, then 11
        # Tank critically low but forecast is good — wait for sun unless
        # someone is actively consuming water (demand detected).
        if not T and not P and W:
            if _demand_detected(s.get('storage_vol_l', 0)):
                return True, True, "01001: demand detected, can't wait for sun — pump+heat"
            return False, False, "01001: waiting for sun (forecast good, no active demand)"

        # 01010 → 00 (NORMAL: 00, FULL: 00 — wait for sun)
        if not T and P and not W:
            return False, False, "01010: forecast good, wait for sun"

        # 01011 → 10  PVT ready, tank critical, forecast good — pump now
        if not T and P and W:
            return True, False, "01011: PVT ready, tank critical, forecast good — pump"

        # 01100 → 00
        if T and not P and not W:
            return False, False, "01100: no sun, forecast ok, tank low temp, PVT cold"

        # 01101 → 00 until demand detected, then 11
        if T and not P and W:
            if _demand_detected(s.get('storage_vol_l', 0)):
                return True, True, "01101: demand detected, can't wait for sun — pump+heat"
            return False, False, "01101: waiting for sun (forecast good, no active demand)"

        # 01110 → 00 (NORMAL: 00, FULL: 00 — wait for sun even though PVT ready)
        if T and P and not W:
            return False, False, "01110: forecast good, wait for solar opportunity"

        # 01111 → 10
        if T and P and W:
            return True, False, "01111: PVT ready, tank critical, temp low, forecast good — pump"

    # ── S=1 H=0 ──────────────────────────────────────────────────────────────
    elif S and not H:
        # 10000 → 00  (if PVT > 55 → 10)
        if not T and not P and not W:
            if zone == 'NORMAL' and pvt_soft_ok:
                return True, False, "10000-NORMAL: sun out, PVT>55°C — pump"
            if pvt_soft_ok:
                return True, False, "10000: sun out, PVT>55°C soft threshold — pump"
            return False, False, "10000: sun out but PVT too cold even for soft threshold"

        # 10001 → 10  (sun out, tank critical — pump assuming PVT > 55)
        if not T and not P and W:
            if pvt_soft_ok:
                return True, False, "10001: sun out, PVT>55°C, tank critical — pump"
            return False, False, "10001: sun out but PVT below soft threshold — wait"

        # 10010 → 00 (NORMAL: 10 if PVT>55)
        if not T and P and not W:
            if zone == 'NORMAL' and pvt_soft_ok:
                return True, False, "10010-NORMAL: sun out, PVT ready — pump"
            return False, False, "10010: tank full, wait"

        # 10011 → 10
        if not T and P and W:
            return True, False, "10011: sun out, PVT ready, tank critical — pump"

        # 10100 → 00
        if T and not P and not W:
            return False, False, "10100: sun out, tank low temp, PVT cold"

        # 10101 → 11  tank critical, temp low, sun out but no forecast — heat+pump
        if T and not P and W:
            return True, True, "10101: critical + temp low + sun out, PVT cold — pump+heat"

        # 10110 → 00 (NORMAL: 10 if PVT>55)
        if T and P and not W:
            if zone == 'NORMAL' and pvt_soft_ok:
                return True, False, "10110-NORMAL: sun out, PVT ready, tank low temp — pump"
            return False, False, "10110: tank full"

        # 10111 → 10
        if T and P and W:
            return True, False, "10111: sun out, PVT ready, tank low+critical — pump"

    # ── S=1 H=1 ──────────────────────────────────────────────────────────────
    elif S and H:
        # 11000 → 00
        if not T and not P and not W:
            return False, False, "11000: sun+forecast good, tank fine, PVT cold"

        # 11001 → 10 (if PVT>55 → 10, else → 11)
        if not T and not P and W:
            if pvt_soft_ok:
                return True, False, "11001: sun+forecast, PVT>55°C, tank critical — pump"
            return True, True, "11001: sun+forecast, PVT cold, tank critical — pump+heat"

        # 11010 → 00 (NORMAL: 10 if PVT>55)
        if not T and P and not W:
            if zone == 'NORMAL' and pvt_soft_ok:
                return True, False, "11010-NORMAL: sun+forecast, PVT ready — pump"
            return False, False, "11010: tank full"

        # 11011 → 10
        if not T and P and W:
            return True, False, "11011: sun+forecast, PVT ready, tank critical — pump"

        # 11100 → 00
        if T and not P and not W:
            return False, False, "11100: sun+forecast, tank low temp, PVT cold, tank full"

        # 11101 → 10 (if PVT>55 → 10, else → 11)
        if T and not P and W:
            if pvt_soft_ok:
                return True, False, "11101: sun+forecast, PVT>55°C, critical, temp low — pump"
            return True, True, "11101: sun+forecast, PVT cold, critical, temp low — pump+heat"

        # 11110 → 00 (NORMAL: 10 if PVT>55)
        if T and P and not W:
            if zone == 'NORMAL' and pvt_soft_ok:
                return True, False, "11110-NORMAL: sun+forecast, PVT ready, temp low — pump"
            return False, False, "11110: tank full"

        # 11111 → 10
        if T and P and W:
            return True, False, "11111: all conditions good — pump"

    # Should never reach here
    return False, False, "UNKNOWN STATE — safe default"


# ── Main control function ─────────────────────────────────────────────────────

def run_control_loop():
    """
    Called repeatedly by main.py on a timer.
    Priority order:
      1. Safety overrides (freeze, overtemperature)
      2. Truth table (pump + heat decision)
      3. LED hysteresis (applied after table output)
    """
    now = time.time()
    print(f"\n{'='*55}")
    print(f"Control loop at t={now}")

    # ── Pull in serial packets (weather + custom data) ────────────────────────
    weather_updates = weather.poll_serial(max_lines=10)
    if weather_updates > 0:
        print(f"  Applied {weather_updates} weather update(s) from serial.")

    # ── Read sensors ──────────────────────────────────────────────────────────
    s = _read_sensors()

    if s is None:
        print("  [TESTING MODE] Waiting for first custom data packet from laptop...")
        print("  Run custom_data_server.py and press Send to begin.")
        return

    print(f"  Sensor source → {'custom test data' if TESTING_MODE else 'physical hardware'}")

    storage_temp = s.get('storage_temp')
    pvt_temp     = s.get('pvt_temp')
    lux          = s.get('lux')
    storage_vol  = s.get('storage_vol_l')
    storage_frac = s.get('storage_frac', 0.0)

    # ── Record LDR reading into trend history ─────────────────────────────────
    if lux is not None:
        ldr_trend.record(lux)

    # ── Record volume into demand-detection buffer ────────────────────────────
    if storage_vol is not None:
        _record_volume(storage_vol)

    # ── SAFETY OVERRIDE 1: Freeze protection ─────────────────────────────────
    temps = [t for t in [storage_temp, pvt_temp] if t is not None]
    if temps and min(temps) <= TEMP_FREEZE_PROTECTION:
        frozen = min(temps)
        print(f"\n[SAFETY] FREEZE PROTECTION — {frozen}°C ≤ {TEMP_FREEZE_PROTECTION}°C")
        actuators.close_valve("Freeze protection")
        actuators.led_on("Freeze protection — heating signal")
        return

    # ── SAFETY OVERRIDE 2: Overtemperature ───────────────────────────────────
    if storage_temp is not None and storage_temp > 80.0:
        print(f"\n[SAFETY] OVERTEMPERATURE — storage at {storage_temp}°C")
        actuators.emergency_stop("Overtemperature")
        return

    # ── Resolve forecast (WiFi → LDR trend fallback) ─────────────────────────
    H = _resolve_forecast(s)
    # Treat unknown forecast (None) as False — conservative default
    H = bool(H) if H is not None else False

    # ── Derive truth table inputs ─────────────────────────────────────────────
    S = bool(s.get('sun_is_out', False))
    T = storage_temp is not None and storage_temp < TEMP_STORAGE_TARGET
    P = bool(s.get('pvt_ready', False))
    W = storage_frac <= 0.20

    # ── Determine tank zone ───────────────────────────────────────────────────
    if storage_frac >= 0.99:
        zone = 'FULL'
    elif storage_frac <= 0.20:
        zone = 'CRITICAL'
    else:
        zone = 'NORMAL'

    _print_snapshot(s, S, H, T, P, W, zone)

    # ── Low water alert (informational only) ──────────────────────────────────
    if zone == 'CRITICAL':
        print(f"\n[ALERT] ⚠️  Storage critically low: {storage_frac*100:.0f}% — consider refill")

    # ── Apply truth table ─────────────────────────────────────────────────────
    pump_on, heat_on, reason = _apply_truth_table(S, H, T, P, W, zone, s)
    print(f"\n[TABLE] Row {int(S)}{int(H)}{int(T)}{int(P)}{int(W)} ({zone}): "
          f"pump={int(pump_on)} heat={int(heat_on)} — {reason}")

    # ── Actuate pump ──────────────────────────────────────────────────────────
    if pump_on:
        actuators.open_valve(reason)
    else:
        actuators.close_valve(reason)

    # ── Actuate LED (heater model) with hysteresis ────────────────────────────
    _apply_led(heat_on, storage_temp, reason)

    print(f"\nControl loop complete.")
