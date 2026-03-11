# main.py
# ─────────────────────────────────────────────────────────────────────────────
# Entry point. Runs after boot.py has connected to Wi-Fi.
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

# ── Fetch initial weather before first control loop ───────────────────────────
print("\nFetching initial weather forecast...")
weather.fetch_forecast()

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
