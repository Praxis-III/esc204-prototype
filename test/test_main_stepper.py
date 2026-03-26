import time
from motor import StepperMotor


# Standalone hardware test: continuously spin the motor.
motor = StepperMotor(
    dir_pin_num=15,
    step_pin_num=14,
    steps_per_rev=500,
    start_delay_us=8000,
    run_delay_us=2000,
    ramp_steps=40,
)

print("Running stepper continuously. Press Ctrl+C to stop.")

num = 0

try:
    while True:
        print("spin")
        num += 1
        motor.move_degrees(360, direction=True)
        time.sleep(2)
except KeyboardInterrupt:
    print("Stepper test stopped.")
