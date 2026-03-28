# actuators.py
# ─────────────────────────────────────────────────────────────────────────────
# Controls all output devices:
#   - DC pump via relay (controls water flow between PVT tank and storage tank)
#   - LED (signals that water would be heated — stands in for a heater)
#
# The pump replaces the previous stepper motor valve. Since the pump is
# simply on or off (no positional state to track), startup initialisation
# just ensures the pump is stopped and state is set to False.
# ─────────────────────────────────────────────────────────────────────────────

import machine
from config import (
    PUMP_RELAY_PIN,
    LED_PIN,
)
from pump import PumpController

# ── Actuator Setup ────────────────────────────────────────────────────────────
_pump = PumpController(
    relay_pin_num=PUMP_RELAY_PIN,
    active_low=True,
    initial_state="off",
)

_led = machine.Pin(LED_PIN, machine.Pin.OUT)

# ── State tracking ────────────────────────────────────────────────────────────
_state = {
    'pump': False,
    'led':  False,
}


# ── Pump control ──────────────────────────────────────────────────────────────

def open_valve(reason=""):
    """Starts the pump — allows water to flow from PVT tank to storage tank."""
    if not _state['pump']:
        print(f"  [PUMP] → ON  ({reason})")
        _pump.run()
        _state['pump'] = True
    else:
        print(f"  [PUMP] already running — no action")

def close_valve(reason=""):
    """Stops the pump — halts water flow."""
    if _state['pump']:
        print(f"  [PUMP] → OFF  ({reason})")
        _pump.stop()
        _state['pump'] = False
    else:
        print(f"  [PUMP] already stopped — no action")

def valve_is_open():
    """Returns True if the pump is currently running."""
    _state['pump'] = _pump.is_running()
    return _state['pump']

def force_set_valve_open():
    """
    Marks pump as running without calling run().
    Use only if external state sync is needed (unlikely with a pump).
    """
    _pump.relay.value(_pump._on_value)
    _state['pump'] = True

def force_set_valve_closed():
    """
    Ensures pump is stopped and state is False.
    Called at startup to establish a known safe state.
    """
    _pump.stop()
    _state['pump'] = False


# ── LED control ───────────────────────────────────────────────────────────────

def led_on(reason=""):
    """Turns LED on — signals that water would be heated in this state."""
    if not _state['led']:
        print(f"  [LED] → ON  ({reason})")
        _led.value(1)
        _state['led'] = True

def led_off(reason=""):
    """Turns LED off."""
    if _state['led']:
        print(f"  [LED] → OFF  ({reason})")
        _led.value(0)
        _state['led'] = False

def led_is_on():
    return _state['led']


# ── Emergency stop ────────────────────────────────────────────────────────────

def emergency_stop(reason="EMERGENCY STOP"):
    """
    Stops pump and turns off LED immediately.
    Safe to call at any time regardless of current state.
    """
    print(f"\n!!! {reason} !!!")
    close_valve(reason)
    led_off(reason)


# ── State summary ─────────────────────────────────────────────────────────────

def get_state():
    """Returns a copy of the current actuator state."""
    return dict(_state)

def print_state():
    s = get_state()
    pump = "ON"  if s['pump'] else "OFF"
    led  = "ON"  if s['led']  else "OFF"
    print(f"  Actuators → Pump:{pump}  LED:{led}")
