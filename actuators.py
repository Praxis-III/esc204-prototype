# actuators.py
# ─────────────────────────────────────────────────────────────────────────────
# Controls all output devices:
#   - Stepper motor valve (opens/closes flow between PVT tank and storage tank)
#   - LED (signals that water would be heated — stands in for a heater)
#
# The stepper motor logic is ported directly from motor.py (your hardware test),
# adapted to be driven by the control system rather than interactive input.
# ─────────────────────────────────────────────────────────────────────────────

import machine
import time
from config import (
    MOTOR_DIR_PIN, MOTOR_STEP_PIN,
    MOTOR_STEPS_PER_REV, MOTOR_START_DELAY_US, MOTOR_RUN_DELAY_US,
    MOTOR_RAMP_STEPS, MOTOR_MOVE_ANGLE, MOTOR_OPEN_DIRECTION,
    LED_PIN,
)

# ── Pin Setup ─────────────────────────────────────────────────────────────────
_dir_pin  = machine.Pin(MOTOR_DIR_PIN,  machine.Pin.OUT)
_step_pin = machine.Pin(MOTOR_STEP_PIN, machine.Pin.OUT)
_step_pin.value(0)

_led = machine.Pin(LED_PIN, machine.Pin.OUT)

# ── Derived motor constants ────────────────────────────────────────────────────
_steps_per_move = int(MOTOR_STEPS_PER_REV * MOTOR_MOVE_ANGLE / 360)

# ── State tracking ─────────────────────────────────────────────────────────────
_state = {
    'valve': False,   # False = closed, True = open
    'led':   False,
}


# ── Internal: step the motor ──────────────────────────────────────────────────

def _step_motor(steps, direction):
    """
    Drives the stepper motor for a given number of steps in a given direction.
    Includes a ramp-up from start_delay to run_delay over the first ramp_steps
    to avoid stalling the motor on sudden starts (ported from motor.py).
    """
    _dir_pin.value(1 if direction else 0)

    for i in range(steps):
        # Linearly interpolate delay from start_delay down to run_delay
        # over the first ramp_steps — after that, run at full speed
        if i < MOTOR_RAMP_STEPS and MOTOR_RAMP_STEPS > 0:
            delay_us = int(
                MOTOR_START_DELAY_US
                - (MOTOR_START_DELAY_US - MOTOR_RUN_DELAY_US) * (i / MOTOR_RAMP_STEPS)
            )
        else:
            delay_us = MOTOR_RUN_DELAY_US

        _step_pin.value(1)
        time.sleep_us(delay_us)
        _step_pin.value(0)
        time.sleep_us(delay_us)


# ── Valve control ─────────────────────────────────────────────────────────────

def open_valve(reason=""):
    """Opens the valve between the PVT model tank and storage tank."""
    if not _state['valve']:
        print(f"  [VALVE] → OPEN  ({reason})")
        _step_motor(_steps_per_move, MOTOR_OPEN_DIRECTION)
        _state['valve'] = True
    else:
        print(f"  [VALVE] already open — no action")

def close_valve(reason=""):
    """Closes the valve between the PVT model tank and storage tank."""
    if _state['valve']:
        print(f"  [VALVE] → CLOSED  ({reason})")
        _step_motor(_steps_per_move, not MOTOR_OPEN_DIRECTION)
        _state['valve'] = False
    else:
        print(f"  [VALVE] already closed — no action")

def valve_is_open():
    return _state['valve']

def force_set_valve_open():
    """
    Marks valve as open without stepping the motor.
    Use this if the physical valve was manually repositioned.
    """
    _state['valve'] = True

def force_set_valve_closed():
    """
    Marks valve as closed without stepping the motor.
    Use this if the physical valve was manually repositioned.
    """
    _state['valve'] = False


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


# ── Emergency stop ─────────────────────────────────────────────────────────────

def emergency_stop(reason="EMERGENCY STOP"):
    """Closes valve and turns off LED immediately."""
    print(f"\n!!! {reason} !!!")
    close_valve(reason)
    led_off(reason)


# ── State summary ──────────────────────────────────────────────────────────────

def get_state():
    """Returns a copy of the current actuator state."""
    return dict(_state)

def print_state():
    s = get_state()
    valve = "OPEN"   if s['valve'] else "CLOSED"
    led   = "ON"     if s['led']   else "OFF"
    print(f"  Actuators → Valve:{valve}  LED:{led}")
