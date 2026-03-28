# test_hardware.py
# ─────────────────────────────────────────────────────────────────────────────
# Run this file instead of main.py when testing on the Pico W without
# the pressure sensor or motor connected.
#
# What is stubbed out:
#   - Stepper motor      → open/close are simulated (no physical stepping)
#   - Pressure sensor    → returns a fixed configurable fill fraction
#
# What runs on REAL hardware:
#   - Storage thermistor → reads actual temperature from GPIO27
#   - PVT thermistor     → reads actual temperature from GPIO28
#   - Photoresistor      → reads actual light level from GPIO26
#   - LED                → physically turns on/off
#   - USB serial         → real custom_data and weather packets from laptop
#   - All control logic  → runs exactly as in production
#
# FIX: Previous version stubbed actuators._step_motor which no longer exists
# as a standalone function. The motor is now encapsulated in StepperMotor.
# This version stubs actuators._motor.step_motor (the instance method) and
# also replaces actuators._motor.open and .close so the motor never physically
# steps while valve state is still tracked correctly.
#
# HOW TO USE:
#   1. Upload this file to the Pico W alongside all other project files
#   2. In Thonny, open this file and press Run (F5)
#   3. Run custom_data_server.py on the laptop and press Send
#   4. Watch the REPL output for each control loop cycle
# ─────────────────────────────────────────────────────────────────────────────

import time
import actuators
import sensors
import controller
import weather
from config import CONTROL_LOOP_INTERVAL_S, STORAGE_TANK_MAX_VOLUME_L

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURE YOUR TEST HERE
# ══════════════════════════════════════════════════════════════════════════════

# Only used if TESTING_MODE = False (physical sensor fallback).
# When TESTING_MODE = True, fill fraction comes from custom_data packets.
FAKE_STORAGE_FRACTION = 0.5

VERBOSE_MOTOR = True

# ══════════════════════════════════════════════════════════════════════════════
# STUB: Stepper motor
# FIX: Stub the instance methods on actuators._motor directly.
# This intercepts all motor movement while preserving is_open state tracking.
# ══════════════════════════════════════════════════════════════════════════════

def _fake_open():
    if not actuators._motor.is_open:
        if VERBOSE_MOTOR:
            print(f"[STUB] Motor would step {actuators._motor.steps_per_move} steps — OPEN direction")
        actuators._motor.is_open = True
    else:
        print("[STUB] Motor already open — no action")

def _fake_close():
    if actuators._motor.is_open:
        if VERBOSE_MOTOR:
            print(f"[STUB] Motor would step {actuators._motor.steps_per_move} steps — CLOSE direction")
        actuators._motor.is_open = False
    else:
        print("[STUB] Motor already closed — no action")

actuators._motor.open  = _fake_open
actuators._motor.close = _fake_close

print(f"[STUB] Stepper motor → simulated (no physical stepping)")

# ══════════════════════════════════════════════════════════════════════════════
# STUB: Pressure sensor (only active when TESTING_MODE = False)
# When TESTING_MODE = True this stub is never called since the controller
# reads from custom_data packets instead of physical sensors.
# ══════════════════════════════════════════════════════════════════════════════

def _fake_volume():
    return round(FAKE_STORAGE_FRACTION * STORAGE_TANK_MAX_VOLUME_L, 2)

def _fake_fraction():
    return FAKE_STORAGE_FRACTION

sensors.read_storage_volume_litres = _fake_volume
sensors.read_storage_fill_fraction = _fake_fraction

print(f"[STUB] Pressure sensor → fixed at {FAKE_STORAGE_FRACTION*100:.0f}% ({_fake_volume()}L) [only used if TESTING_MODE=False]")

# ══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*55)
print("  PVT Controller — HARDWARE TEST MODE")
print("  Real:    thermistors, photoresistor, LED, serial")
print("  Stubbed: stepper motor, pressure sensor")
print("="*55)

actuators.emergency_stop("Startup: safe state")

print("\nWaiting for initial weather packet on USB serial...")
if weather.wait_for_initial_forecast(timeout_s=5) is None:
    print("  No weather packet yet. Continuing — will update when received.")

print(f"\nEntering control loop (interval: {CONTROL_LOOP_INTERVAL_S}s)")
print("Run custom_data_server.py on the laptop and press Send to begin.\n")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

while True:
    try:
        controller.run_control_loop()
    except Exception as e:
        print(f"\n!!! ERROR in control loop: {e}")
        print("  Entering safe state and retrying in 60s...")
        actuators.emergency_stop("Error recovery")
        time.sleep(60)
        continue

    time.sleep(CONTROL_LOOP_INTERVAL_S)
