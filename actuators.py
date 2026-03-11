# actuators.py
# ─────────────────────────────────────────────────────────────────────────────
# Controls all output devices:
#   - Supply tank valve motor   (opens flow from supply → PVT)
#   - Storage tank valve motor  (opens flow from PVT → storage)
#   - Electric heater relay
# ─────────────────────────────────────────────────────────────────────────────

import machine
from config import MOTOR_SUPPLY_PIN, MOTOR_STORAGE_PIN, HEATER_PIN

# ── Pin Setup ─────────────────────────────────────────────────────────────────
# We use simple digital outputs. If your motor requires PWM or a motor driver
# board (e.g. L298N), the Pin.value() calls below will need to be adapted.
# For a relay-controlled valve solenoid, this works directly.

_motor_supply  = machine.Pin(MOTOR_SUPPLY_PIN,  machine.Pin.OUT)
_motor_storage = machine.Pin(MOTOR_STORAGE_PIN, machine.Pin.OUT)
_heater        = machine.Pin(HEATER_PIN,         machine.Pin.OUT)

# Track state so we can log changes without spamming
_state = {
    'supply_valve':  False,
    'storage_valve': False,
    'heater':        False,
}


def _set(pin, name, value, reason=""):
    """Internal helper — sets a pin and logs state changes."""
    if _state[name] != value:
        status = "ON" if value else "OFF"
        print(f"  [{name.upper()}] → {status}  ({reason})")
        _state[name] = value
    pin.value(1 if value else 0)


# ── Supply Valve ──────────────────────────────────────────────────────────────

def open_supply_valve(reason=""):
    """Open supply tank valve — allows water to flow from supply into PVT."""
    _set(_motor_supply, 'supply_valve', True, reason)

def close_supply_valve(reason=""):
    """Close supply tank valve — stops flow from supply tank."""
    _set(_motor_supply, 'supply_valve', False, reason)

def supply_valve_is_open():
    return _state['supply_valve']


# ── Storage Valve ─────────────────────────────────────────────────────────────

def open_storage_valve(reason=""):
    """Open storage tank valve — allows hot water to flow from PVT into storage."""
    _set(_motor_storage, 'storage_valve', True, reason)

def close_storage_valve(reason=""):
    """Close storage tank valve."""
    _set(_motor_storage, 'storage_valve', False, reason)

def storage_valve_is_open():
    return _state['storage_valve']


# ── Heater ────────────────────────────────────────────────────────────────────

def heater_on(reason=""):
    """Turn electric heater ON."""
    _set(_heater, 'heater', True, reason)

def heater_off(reason=""):
    """Turn electric heater OFF."""
    _set(_heater, 'heater', False, reason)

def heater_is_on():
    return _state['heater']


# ── Emergency Stop ────────────────────────────────────────────────────────────

def emergency_stop(reason="EMERGENCY STOP"):
    """Closes all valves and turns off heater immediately."""
    print(f"\n!!! {reason} !!!")
    close_supply_valve(reason)
    close_storage_valve(reason)
    heater_off(reason)


# ── State Summary ─────────────────────────────────────────────────────────────

def get_state():
    """Returns a copy of the current actuator state dict."""
    return dict(_state)

def print_state():
    s = get_state()
    supply  = "OPEN" if s['supply_valve']  else "CLOSED"
    storage = "OPEN" if s['storage_valve'] else "CLOSED"
    heater  = "ON"   if s['heater']        else "OFF"
    print(f"  Actuators → Supply:{supply}  Storage:{storage}  Heater:{heater}")
