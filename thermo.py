import time
import analogio
import math
from config import THERMISTOR_PIN

class Thermistor:
    def __init__(self):
        # Hardware
        self.thermistor = analogio.AnalogIn(THERMISTOR_PIN)

        # ADC
        self.ADC_HIGH = 65535
        self.ADC_REF = self.thermistor.reference_voltage

        # Thermistor parameters
        self.NOMINAL_RESISTANCE = 10000.0
        self.NOMINAL_TEMPERATURE = 25.0
        self.B_COEFFICIENT = 3820.0
        self.SERIES_RESISTOR = 10000.0
        self.THERM_OFFSET = -1.0

    # ===== HELPER =====
    def read_avg(self, samples=10):
        total = 0
        for _ in range(samples):
            total += self.thermistor.value
        return total // samples

    # ===== THERMISTOR CALC =====
    def get_temp_c(self, adc_value):
        if adc_value <= 0:
            return -273.15

        resistance = self.SERIES_RESISTOR / (self.ADC_HIGH / adc_value - 1)

        steinhart = resistance / self.NOMINAL_RESISTANCE
        steinhart = math.log(steinhart)
        steinhart /= self.B_COEFFICIENT
        steinhart += 1.0 / (self.NOMINAL_TEMPERATURE + 273.15)
        steinhart = 1.0 / steinhart

        return steinhart - 273.15 + self.THERM_OFFSET

    # ===== MAIN OUTPUT =====
    def output(self):
        adc = self.read_avg()
        temp_c = self.get_temp_c(adc)
        return round(temp_c, 2)