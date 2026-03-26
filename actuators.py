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
from motor import StepperMotor
# ── Actuator Setup ────────────────────────────────────────────────────────────
_motor = StepperMotor(
    dir_pin_num=MOTOR_DIR_PIN,
    step_pin_num=MOTOR_STEP_PIN,
    steps_per_rev=MOTOR_STEPS_PER_REV,
    start_delay_us=MOTOR_START_DELAY_US,
    run_delay_us=MOTOR_RUN_DELAY_US,
    ramp_steps=MOTOR_RAMP_STEPS,
    move_angle=MOTOR_MOVE_ANGLE,
    open_direction=MOTOR_OPEN_DIRECTION,
)

_led = machine.Pin(LED_PIN, machine.Pin.OUT)

# ── State tracking ─────────────────────────────────────────────────────────────
_state = {
    'valve': False,   # False = closed, True = open
    'led':   False,
}


# ── Valve control ─────────────────────────────────────────────────────────────

def open_valve(reason=""):
    """Opens the valve between the PVT model tank and storage tank."""
    if not _state['valve']:
        print(f"  [VALVE] → OPEN  ({reason})")
        _motor.open()
        _state['valve'] = _motor.is_open
    else:
        print(f"  [VALVE] already open — no action")

def close_valve(reason=""):
    """Closes the valve between the PVT model tank and storage tank."""
    if _state['valve']:
        print(f"  [VALVE] → CLOSED  ({reason})")
        _motor.close()
        _state['valve'] = _motor.is_open
    else:
        print(f"  [VALVE] already closed — no action")

def valve_is_open():
    _state['valve'] = _motor.is_open
    return _state['valve']

def force_set_valve_open():
    """
    Marks valve as open without stepping the motor.
    Use this if the physical valve was manually repositioned.
    """
    _motor.set_position_open()
    _state['valve'] = True

def force_set_valve_closed():
    """
    Marks valve as closed without stepping the motor.
    Use this if the physical valve was manually repositioned.
    """
    _motor.set_position_closed()
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
