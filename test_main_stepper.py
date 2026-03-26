import time
from motor import StepperMotor


# Standalone hardware test: continuously spin the motor.
motor = StepperMotor(
    dir_pin_num=16,
    step_pin_num=17,
    steps_per_rev=500,
    start_delay_us=8000,
    run_delay_us=2000,
    ramp_steps=40,
)

print("Running stepper continuously. Press Ctrl+C to stop.")

try:
    while True:
        print("spin")
        motor.open()
        time.sleep(1)
        motor.close()
        time.sleep(1)
except KeyboardInterrupt:
    print("Stepper test stopped.")
