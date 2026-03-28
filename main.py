# main.py
# ─────────────────────────────────────────────────────────────────────────────
# Entry point. Weather data is fed over USB serial from a laptop-side script.
# Starts the control loop and keeps it running forever.
# ─────────────────────────────────────────────────────────────────────────────

import time
import controller
import actuators
import weather
from config import CONTROL_LOOP_INTERVAL_S

print("\n" + "="*55)
print("  PVT Solar Control System — Starting Up")
print("="*55)

# ── Initial safety state: everything off ──────────────────────────────────────
actuators.emergency_stop("Startup: initialising to safe state")

# ── Optionally wait briefly for first serial weather packet ───────────────────
print("\nWaiting briefly for initial weather packet on USB serial...")
if weather.wait_for_initial_forecast(timeout_s=5) is None:
    print("  No weather packet received yet. Continuing with unknown forecast.")

# ── Main loop ─────────────────────────────────────────────────────────────────
print(f"\nEntering control loop (interval: {CONTROL_LOOP_INTERVAL_S}s)\n")

while True:
    try:
        controller.run_control_loop()
    except Exception as e:
        # If something unexpected crashes the control loop, log it and
        # go to a safe state rather than crashing the whole program.
        print(f"\n!!! UNHANDLED ERROR in control loop: {e} !!!")
        print("  Entering safe state and retrying in 60 seconds...")
        actuators.emergency_stop("Unhandled error — safe state")
        time.sleep(60)
        continue

    time.sleep(CONTROL_LOOP_INTERVAL_S)
