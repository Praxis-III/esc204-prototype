# pump.py
# ─────────────────────────────────────────────────────────────────────────────
# Controls the solar DC water pump (JAVTOP JT280T) via a relay module.
# The relay is active-low: GPIO LOW = relay ON = pump running.
# ─────────────────────────────────────────────────────────────────────────────

import time
from machine import Pin


class PumpController:
    def __init__(self, relay_pin_num, active_low=True, initial_state="off"):
        """
        relay_pin_num : GPIO number connected to relay S pin
        active_low    : True if relay turns ON when pin is LOW (default)
        initial_state : "off" or "on"
        """
        self.relay = Pin(relay_pin_num, Pin.OUT)
        self.active_low = active_low

        if self.active_low:
            self._on_value  = 0
            self._off_value = 1
        else:
            self._on_value  = 1
            self._off_value = 0

        if initial_state == "on":
            self.run()
        else:
            self.stop()

    def run(self):
        """Turn pump ON."""
        self.relay.value(self._on_value)

    def stop(self):
        """Turn pump OFF."""
        self.relay.value(self._off_value)

    def toggle(self):
        """Toggle current relay state."""
        self.relay.value(0 if self.relay.value() else 1)

    def is_running(self):
        """Return True if pump is currently ON."""
        return self.relay.value() == self._on_value

    def run_for(self, seconds):
        """Run pump for a fixed duration, then stop."""
        self.run()
        time.sleep(seconds)
        self.stop()
