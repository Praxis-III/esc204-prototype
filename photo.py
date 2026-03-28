import time
import analogio
from config import PHOTERESISTOR_PIN

class Photo:
    def __init__(self):
        # Hardware
        self.photoresistor = analogio.AnalogIn(PHOTORESISTOR_PIN)
        self.ADC_HIGH = 65535
        self.ADC_REF = self.photoresistor.reference_voltage

        # Circuit constants
        self.LDR_FIXED_RESISTOR = 10000.0

        # Calibration constants
        self.A_CONST = 500000.0
        self.B_CONST = 1.4

    # ===== HELPER: AVERAGE ADC =====
    def read_avg(self, samples=10):
        total = 0
        for _ in range(samples):
            total += self.photoresistor.value
        return total // samples

    # ===== ADC → VOLTAGE =====
    def adc_to_voltage(self, adc):
        return self.ADC_REF * adc / self.ADC_HIGH

    # ===== VOLTAGE → RESISTANCE =====
    def voltage_to_ldr_resistance(self, v):
        if v <= 0.001:
            return 1e9
        return self.LDR_FIXED_RESISTOR * (self.ADC_REF - v) / v

    # ===== RESISTANCE → LUX =====
    def resistance_to_lux(self, resistance):
        return (self.A_CONST / resistance) ** (1.0 / self.B_CONST)

    # ===== MAIN OUTPUT =====
    def output(self):
        ldr_adc = self.read_avg()
        ldr_voltage = self.adc_to_voltage(ldr_adc)
        ldr_resistance = self.voltage_to_ldr_resistance(ldr_voltage)
        lux = self.resistance_to_lux(ldr_resistance)

        return round(lux, 2)