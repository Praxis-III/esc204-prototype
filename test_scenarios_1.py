import sys
sys.path.insert(0, '.')

import time
time.sleep_ms = lambda ms: time.sleep(ms / 1000)

import machine
import ds18x20
import config

# ── Set sensor addresses BEFORE importing sensors/controller ──────────────────
config.DS18B20_STORAGE_TOP    = bytearray(b'\x28\x01\x00\x00\x00\x00\x00\x01')
config.DS18B20_STORAGE_MID    = bytearray(b'\x28\x02\x00\x00\x00\x00\x00\x02')
config.DS18B20_STORAGE_BOTTOM = bytearray(b'\x28\x03\x00\x00\x00\x00\x00\x03')
config.DS18B20_PVT            = bytearray(b'\x28\x04\x00\x00\x00\x00\x00\x04')

import sensors
import actuators
import weather
import controller

# ── Mock helpers ──────────────────────────────────────────────────────────────

def set_storage_temps(top, mid, bottom):
    ds18x20.DS18X20._mock_temps[bytes(config.DS18B20_STORAGE_TOP)]    = top
    ds18x20.DS18X20._mock_temps[bytes(config.DS18B20_STORAGE_MID)]    = mid
    ds18x20.DS18X20._mock_temps[bytes(config.DS18B20_STORAGE_BOTTOM)] = bottom

def set_pvt_temp(temp):
    ds18x20.DS18X20._mock_temps[bytes(config.DS18B20_PVT)] = temp

def set_ldr(raw_value):
    machine.ADC._mock_values[config.PHOTORESISTOR_PIN] = raw_value

def set_pressure(fraction):
    v_range = config.PRESSURE_VOLTAGE_AT_FULL - config.PRESSURE_VOLTAGE_AT_EMPTY
    volts = config.PRESSURE_VOLTAGE_AT_EMPTY + fraction * v_range
    raw = int((volts / 3.3) * 65535)
    machine.ADC._mock_values[config.PRESSURE_PIN] = raw

def set_supply_fraction(frac):
    controller._MOCK_SUPPLY_FRACTION = frac

def set_sunny_forecast(is_sunny=True):
    if is_sunny:
        weather._cache['data'] = [
            {'time': f'T{h:02d}:00', 'cloudcover': 10, 'precip_mm': 0.0, 'air_temp_c': 15.0}
            for h in range(24)
        ]
    else:
        weather._cache['data'] = [
            {'time': f'T{h:02d}:00', 'cloudcover': 90, 'precip_mm': 2.0, 'air_temp_c': 10.0}
            for h in range(24)
        ]
    weather._cache['fetched_at'] = time.time()

def reset_all():
    actuators.emergency_stop("test reset")
    controller._pvt_flow_started_at   = None
    controller._cloud_transient_start = None

def get_state():
    return actuators.get_state()

# ── Patch supply fraction ─────────────────────────────────────────────────────
controller._MOCK_SUPPLY_FRACTION = 1.0
controller._estimate_supply_fraction = lambda s: controller._MOCK_SUPPLY_FRACTION

# ── Test runner ───────────────────────────────────────────────────────────────
PASS = 0
FAIL = 0

def run_test(name, setup_fn, check_fn):
    global PASS, FAIL
    print(f"\n{'─'*58}")
    print(f"TEST: {name}")
    print('─'*58)
    reset_all()
    setup_fn()
    controller.run_control_loop()
    state = get_state()
    result, message = check_fn(state)
    if result:
        print(f"  ✅  PASS — {message}")
        PASS += 1
    else:
        print(f"  ❌  FAIL — {message}")
        print(f"       State: {state}")
        FAIL += 1

# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

def setup_case1():
    set_storage_temps(58, 55, 52); set_pvt_temp(20.0)
    set_ldr(50000); set_pressure(0.5)
    set_supply_fraction(1.0); set_sunny_forecast(True)

run_test("Case 1 — Sun out + good forecast → supply valve opens",
    setup_case1,
    lambda s: (s['supply_valve'] and not s['storage_valve'],
               "Supply OPEN, storage CLOSED (PVT not hot yet)"))

def setup_case1b():
    set_storage_temps(58, 55, 52); set_pvt_temp(20.0)
    set_ldr(5000); set_pressure(0.5)
    set_supply_fraction(1.0); set_sunny_forecast(False)

run_test("Case 1b — No sun + bad forecast → valves stay closed",
    setup_case1b,
    lambda s: (not s['supply_valve'] and not s['storage_valve'],
               "Both valves correctly CLOSED"))

def setup_case2():
    set_storage_temps(55, 53, 50); set_pvt_temp(62.0)   # PVT above 60C
    set_ldr(50000); set_pressure(0.5)
    set_supply_fraction(1.0); set_sunny_forecast(True)

run_test("Case 2 — PVT at 62°C → both valves open, fill storage",
    setup_case2,
    lambda s: (s['supply_valve'] and s['storage_valve'],
               "Both valves OPEN — filling storage from hot PVT"))

def setup_case3():
    set_storage_temps(60, 58, 55); set_pvt_temp(25.0)
    set_ldr(50000); set_pressure(0.5)
    set_supply_fraction(0.15)   # Below 20% threshold
    set_sunny_forecast(True)

run_test("Case 3 — Supply tank at 15% → emergency refill",
    setup_case3,
    lambda s: (s['supply_valve'] and s['storage_valve'],
               "Both valves OPEN for emergency refill"))

def setup_case3b():
    set_storage_temps(51, 50, 49); set_pvt_temp(10.0)   # Cold PVT — mixing drops temp
    set_ldr(5000); set_pressure(0.8)
    set_supply_fraction(0.10)
    set_sunny_forecast(False)

run_test("Case 3b — Emergency refill + cold PVT → heater on",
    setup_case3b,
    lambda s: (s['heater'],
               "Heater ON — mixing would drop below 50°C minimum"))

def setup_case4():
    set_storage_temps(3.0, 2.5, 2.0); set_pvt_temp(1.5)   # Near freezing
    set_ldr(10000); set_pressure(0.4)
    set_supply_fraction(1.0); set_sunny_forecast(False)

run_test("Case 4 — Near-freezing temps → freeze protection",
    setup_case4,
    lambda s: (s['storage_valve'] and not s['supply_valve'] and s['heater'],
               "Storage valve OPEN (drain PVT), supply CLOSED, heater ON"))

def setup_case5():
    set_storage_temps(85.0, 78.0, 72.0); set_pvt_temp(90.0)   # Overtemp!
    set_ldr(60000); set_pressure(0.9)
    set_supply_fraction(1.0); set_sunny_forecast(True)

run_test("Case 5 — Storage top at 85°C → emergency stop",
    setup_case5,
    lambda s: (not s['supply_valve'] and not s['storage_valve'] and not s['heater'],
               "All outputs OFF on overtemperature"))

def setup_case6a():
    set_storage_temps(51, 51, 51)   # All below heater-on threshold (52°C)
    set_pvt_temp(20.0)
    set_ldr(5000); set_pressure(0.7)
    set_supply_fraction(1.0); set_sunny_forecast(False)

run_test("Case 6a — Storage avg 51°C → heater turns on",
    setup_case6a,
    lambda s: (s['heater'],
               f"Heater ON at 51°C (threshold={config.TEMP_STORAGE_HEATER_ON}°C)"))

def setup_case6b():
    actuators.heater_on("pre-condition")   # heater already on
    set_storage_temps(61, 61, 61)   # Above heater-off threshold (60°C)
    set_pvt_temp(20.0)
    set_ldr(5000); set_pressure(0.7)
    set_supply_fraction(1.0); set_sunny_forecast(False)

run_test("Case 6b — Storage at 61°C, heater was on → heater turns off",
    setup_case6b,
    lambda s: (not s['heater'],
               f"Heater OFF at 61°C (threshold={config.TEMP_STORAGE_HEATER_OFF}°C)"))

def setup_case8():
    set_storage_temps(60, 60, 60); set_pvt_temp(65.0)   # PVT hot but storage full
    set_ldr(55000); set_pressure(1.0)                    # 100% full
    set_supply_fraction(1.0); set_sunny_forecast(True)

run_test("Case 8 — Storage 100% full → stop filling",
    setup_case8,
    lambda s: (not s['supply_valve'] and not s['storage_valve'],
               "Both valves CLOSED — no overflow"))

def setup_case10():
    set_storage_temps(56, 55, 54)   # Below target but above minimum
    set_pvt_temp(20.0)
    set_ldr(5000); set_pressure(0.6)
    set_supply_fraction(1.0); set_sunny_forecast(False)   # No sun all day

run_test("Case 10 — No sun forecast + storage below target → pre-emptive heating",
    setup_case10,
    lambda s: (s['heater'],
               "Heater ON — no solar expected, grid pre-heat"))

# ── Mixing temp arithmetic ────────────────────────────────────────────────────
print(f"\n{'─'*58}")
print("TEST: Mixing temperature calculation (100L@60°C + 20L@10°C)")
print('─'*58)
mixed    = sensors.estimate_mixed_temp(60.0, 10.0, 100.0, 20.0)
expected = (60*100 + 10*20) / 120
if abs(mixed - expected) < 0.01:
    print(f"  ✅  PASS — Mixed temp = {mixed:.2f}°C  (expected {expected:.2f}°C)")
    PASS += 1
else:
    print(f"  ❌  FAIL — Mixed temp = {mixed:.2f}°C  (expected {expected:.2f}°C)")
    FAIL += 1

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*58}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed  ({PASS+FAIL} total)")
print('='*58)
if FAIL == 0:
    print("  🎉  All tests passed!")
else:
    print(f"  ⚠️   {FAIL} test(s) need attention — see details above.")
