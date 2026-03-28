import time
from machine import Pin


class StepperMotor:
    def __init__(
        self,
        dir_pin_num,
        step_pin_num,
        steps_per_rev=500,
        start_delay_us=8000,
        run_delay_us=2000,
        ramp_steps=40,
        move_angle=90,
        open_direction=True
    ):
        self.dir_pin = Pin(dir_pin_num, Pin.OUT)
        self.step_pin = Pin(step_pin_num, Pin.OUT)
        self.step_pin.value(0)

        self.steps_per_rev = steps_per_rev
        self.start_delay_us = start_delay_us
        self.run_delay_us = run_delay_us
        self.ramp_steps = ramp_steps

        self.move_angle = move_angle
        self.steps_per_move = int(self.steps_per_rev * self.move_angle / 360)

        self.open_direction = open_direction
        self.is_open = False

    def step_motor(self, steps, direction):
        self.dir_pin.value(1 if direction else 0)

        for i in range(steps):
            if i < self.ramp_steps and self.ramp_steps > 0:
                delay_us = int(
                    self.start_delay_us
                    - (self.start_delay_us - self.run_delay_us) * (i / self.ramp_steps)
                )
            else:
                delay_us = self.run_delay_us

            self.step_pin.value(1)
            time.sleep_us(delay_us)
            self.step_pin.value(0)
            time.sleep_us(delay_us)

    def open(self):
        if not self.is_open:
            self.step_motor(self.steps_per_move, self.open_direction)
            self.is_open = True
            print("Opened")
        else:
            print("Already open")

    def close(self):
        if self.is_open:
            self.step_motor(self.steps_per_move, not self.open_direction)
            self.is_open = False
            print("Closed")
        else:
            print("Already closed")

    def move_degrees(self, angle, direction=True):
        steps = int(self.steps_per_rev * angle / 360)
        self.step_motor(steps, direction)

    def set_open_direction(self, direction_bool):
        self.open_direction = direction_bool

    def set_position_closed(self):
        self.is_open = False

    def set_position_open(self):
        self.is_open = True