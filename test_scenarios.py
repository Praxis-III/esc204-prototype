import sys, math, time
sys.path.insert(0, '.')
time.sleep_ms = lambda ms: time.sleep(ms/1000)
time.sleep_us = lambda us: time.sleep(us/1_000_000)

import machine, config, custom_data

# ── Helpers to inject custom_data snapshots directly ──────────────────────────

def inject(storage_temp=55.0, pvt_temp=35.0, lux=50.0,
           tank_pct=50.0, forecast_ok=False):
    """Directly injects a snapshot into custom_data cache."""
    custom_data.ingest_serial_payload({
        "tank_capacity_pct": tank_pct,
        "solar_lux":         lux,
        "pvt_temp_c":        pvt_temp,
        "tank_temp_c":       storage_temp,
        "next_hour_solar_available": forecast_ok,
    })

import actuators, weather, controller

# Force testing mode on
import config as _cfg
_cfg.TESTING_MODE = True

def reset_all():
    actuators.emergency_stop("test reset")
    controller._valve_opened_at       = None
    controller._cloud_transient_start = None
    # Clear custom data cache
    custom_data._cache['snapshot'] = None

PASS = 0
FAIL = 0

def run_test(name, setup_fn, check_fn):
    global PASS, FAIL
    print(f"\n{'─'*60}")
    print(f"TEST: {name}")
    print('─'*60)
    reset_all()
    setup_fn()
    controller.run_control_loop()
    state = actuators.get_state()
    result, message = check_fn(state)
    if result:
        print(f"  ✅  PASS — {message}")
        PASS += 1
    else:
        print(f"  ❌  FAIL — {message}  |  state={state}")
        FAIL += 1

# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

# Case 1: All three conditions met → valve opens
run_test("Case 1 — Sun + PVT hot + good forecast → valve opens",
    lambda: inject(storage_temp=55, pvt_temp=62, lux=2000, tank_pct=50, forecast_ok=True),
    lambda s: (s['valve'], "Valve OPEN"))

# Case 1b: Sun out but PVT cold → wait
run_test("Case 1b — Sun out but PVT 35°C → valve stays closed (waiting for PVT)",
    lambda: inject(storage_temp=55, pvt_temp=35, lux=2000, tank_pct=50, forecast_ok=True),
    lambda s: (not s['valve'], "Valve CLOSED — PVT not ready"))

# Case 1c: PVT hot but no sun → closed
run_test("Case 1c — PVT hot but no sun (lux=50) → valve stays closed",
    lambda: inject(storage_temp=55, pvt_temp=65, lux=50, tank_pct=50, forecast_ok=True),
    lambda s: (not s['valve'], "Valve CLOSED — no sun"))

# Case 1d: PVT hot, sun out, but bad forecast → closed
run_test("Case 1d — PVT hot + sun out but bad forecast → valve stays closed",
    lambda: inject(storage_temp=55, pvt_temp=65, lux=2000, tank_pct=50, forecast_ok=False),
    lambda s: (not s['valve'], "Valve CLOSED — bad forecast"))

# Case 2: Storage full → close
run_test("Case 2 — Storage 100% full → valve closes",
    lambda: inject(storage_temp=58, pvt_temp=65, lux=2000, tank_pct=100, forecast_ok=True),
    lambda s: (not s['valve'], "Valve CLOSED — no overflow"))

# Case 3: Low water → alert only
run_test("Case 3 — Storage at 10% → alert printed, no hardware change",
    lambda: inject(storage_temp=58, pvt_temp=35, lux=50, tank_pct=10, forecast_ok=False),
    lambda s: (not s['valve'], "No hardware action — alert printed"))

# Case 4a: Storage near freezing
run_test("Case 4a — Storage temp 2°C → freeze protection",
    lambda: inject(storage_temp=2, pvt_temp=20, lux=50, tank_pct=50, forecast_ok=False),
    lambda s: (not s['valve'] and s['led'], "Valve CLOSED, LED ON"))

# Case 4b: PVT near freezing
run_test("Case 4b — PVT temp 1°C → freeze protection",
    lambda: inject(storage_temp=55, pvt_temp=1, lux=50, tank_pct=50, forecast_ok=False),
    lambda s: (not s['valve'] and s['led'], "Valve CLOSED, LED ON"))

# Case 5: Overtemperature
run_test("Case 5 — Storage at 85°C → emergency stop",
    lambda: inject(storage_temp=85, pvt_temp=65, lux=2000, tank_pct=70, forecast_ok=True),
    lambda s: (not s['valve'] and not s['led'], "All outputs OFF"))

# Case 6a: LED on
run_test("Case 6a — Storage at 51°C → LED on",
    lambda: inject(storage_temp=51, pvt_temp=35, lux=50, tank_pct=60, forecast_ok=False),
    lambda s: (s['led'], f"LED ON (threshold={config.TEMP_STORAGE_LED_ON}°C)"))

# Case 6b: LED off
def setup_6b():
    actuators.led_on("pre-condition")
    inject(storage_temp=61, pvt_temp=35, lux=50, tank_pct=60, forecast_ok=False)
run_test("Case 6b — Storage at 61°C, LED was on → LED off",
    setup_6b,
    lambda s: (not s['led'], f"LED OFF (threshold={config.TEMP_STORAGE_LED_OFF}°C)"))

# Case 9: Pre-emptive LED
run_test("Case 9 — No sun forecast + storage below target → LED on",
    lambda: inject(storage_temp=56, pvt_temp=35, lux=50, tank_pct=60, forecast_ok=False),
    lambda s: (s['led'], "LED ON pre-emptive"))

# ── custom_data sun_is_out fix verification ────────────────────────────────────
print(f"\n{'─'*60}")
print("TEST: custom_data — sun_is_out uses lux not forecast_ok")
print('─'*60)
# forecast_ok=True but lux=50 (dark) → sun_is_out must be False
custom_data.ingest_serial_payload({
    "tank_capacity_pct": 50, "solar_lux": 50,
    "pvt_temp_c": 65, "tank_temp_c": 55,
    "next_hour_solar_available": True
})
snap = custom_data.get_latest_snapshot()
if snap['sun_is_out'] == False and snap['sun_forecast_ok'] == True:
    print(f"  ✅  PASS — sun_is_out=False (lux=50), sun_forecast_ok=True (correctly separated)")
    PASS += 1
else:
    print(f"  ❌  FAIL — sun_is_out={snap['sun_is_out']}, sun_forecast_ok={snap['sun_forecast_ok']}")
    FAIL += 1

# ── No custom data → loop waits gracefully ────────────────────────────────────
print(f"\n{'─'*60}")
print("TEST: No custom data received → loop skips gracefully (no crash)")
print('─'*60)
reset_all()
# Don't inject anything — cache is None
try:
    controller.run_control_loop()
    print("  ✅  PASS — Loop returned without crash")
    PASS += 1
except Exception as e:
    print(f"  ❌  FAIL — Crashed with: {e}")
    FAIL += 1

print(f"\n{'='*60}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed  ({PASS+FAIL} total)")
print('='*60)
print("  🎉  All tests passed!" if FAIL == 0 else f"  ⚠️   {FAIL} test(s) need attention.")
