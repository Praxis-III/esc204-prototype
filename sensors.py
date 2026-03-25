# sensors.py
# ─────────────────────────────────────────────────────────────────────────────
# Handles all sensor reading:
#   - Storage tank thermistor (10K Precision Epoxy, GPIO27)
#   - PVT tank thermistor    (same type, GPIO28)
#   - Photoresistor / LDR    (lux conversion, GPIO26)
#   - Pressure sensor        (analog ADC → volume in litres, GPIO22 placeholder)
#
# Both thermistors are identical in type and share the same calibration
# constants from config.py. They are read independently via separate ADC pins.
#
# All sensors use MicroPython's machine.ADC (16-bit, 0–65535, 3.3V reference).
# ─────────────────────────────────────────────────────────────────────────────

import machine
import math
import time
from config import (
    THERMISTOR_STORAGE_PIN, THERMISTOR_PVT_PIN,
    PHOTORESISTOR_PIN,
    THERM_NOMINAL_RESISTANCE, THERM_NOMINAL_TEMP_C,
    THERM_B_COEFFICIENT, THERM_SERIES_RESISTOR, THERM_OFFSET,
    LDR_FIXED_RESISTOR, LDR_A_CONST, LDR_B_CONST,
    LDR_SUNLIGHT_LUX, LDR_BRIGHT_SUN_LUX,
    PRESSURE_DATA_PIN, PRESSURE_CLOCK_PIN,
    PRESSURE_CALIBRATION_FACTOR,
    PRESSURE_SAMPLE_COUNT, PRESSURE_SAMPLE_DELAY_S,
    PRESSURE_TARE_SAMPLES,
    PRESSURE_EMA_ALPHA, PRESSURE_DRIFT_ALPHA,
    PRESSURE_DRIFT_THRESHOLD_KG, PRESSURE_DEADBAND_KG,
    STORAGE_TANK_MAX_VOLUME_L,
)

# ── ADC Setup ─────────────────────────────────────────────────────────────────
_therm_storage_adc = machine.ADC(THERMISTOR_STORAGE_PIN)
_therm_pvt_adc     = machine.ADC(THERMISTOR_PVT_PIN)
_ldr_adc           = machine.ADC(PHOTORESISTOR_PIN)

# Pico W: 16-bit ADC, 3.3V reference
_ADC_MAX = 65535
_VREF    = 3.3


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_avg(adc, samples=10):
    """Reads an ADC pin multiple times and returns the integer average.
    Averaging reduces noise on analog readings."""
    total = 0
    for _ in range(samples):
        total += adc.read_u16()
    return total // samples

def _adc_to_voltage(raw):
    """Converts a raw 16-bit ADC value to voltage (0–3.3V)."""
    return _VREF * raw / _ADC_MAX

def _resistance_from_voltage(voltage):
    """
    Converts ADC voltage to thermistor resistance.
    Divider: Vref → Rs → ADC → R_therm → GND  (thermistor on bottom)
    R_therm = Rs * V / (Vref - V)
    """
    if voltage >= _VREF or voltage <= 0:
        return None
    return THERM_SERIES_RESISTOR * voltage / (_VREF - voltage)

def _resistance_to_temp_c(resistance):
    """
    Converts thermistor resistance to temperature in °C using the
    Steinhart-Hart B-parameter equation:
        1/T = 1/T0 + (1/B) * ln(R/R0)
    """
    if resistance is None or resistance <= 0:
        return None
    steinhart  = resistance / THERM_NOMINAL_RESISTANCE
    steinhart  = math.log(steinhart)
    steinhart /= THERM_B_COEFFICIENT
    steinhart += 1.0 / (THERM_NOMINAL_TEMP_C + 273.15)
    temp_c     = (1.0 / steinhart) - 273.15 + THERM_OFFSET
    return round(temp_c, 2)

def _read_thermistor(adc):
    """Reads a thermistor from a given ADC and returns temperature in °C."""
    raw        = _read_avg(adc)
    voltage    = _adc_to_voltage(raw)
    resistance = _resistance_from_voltage(voltage)
    return _resistance_to_temp_c(resistance)


# ── Thermistors ───────────────────────────────────────────────────────────────

def read_storage_temp_c():
    """
    Reads the storage tank thermistor (GPIO27).
    Returns temperature in °C, or None on failure.
    """
    return _read_thermistor(_therm_storage_adc)

def read_pvt_temp_c():
    """
    Reads the PVT model tank thermistor (GPIO28).
    Returns temperature in °C, or None on failure.
    """
    return _read_thermistor(_therm_pvt_adc)


# ── Photoresistor / LDR ───────────────────────────────────────────────────────

def _ldr_resistance(voltage):
    """Converts LDR voltage divider output to LDR resistance.
    Divider: Vref → LDR → ADC → R_fixed → GND
    """
    if voltage <= 0.001:
        return 1e9
    return LDR_FIXED_RESISTOR * (_VREF - voltage) / voltage

def _resistance_to_lux(resistance):
    """Converts LDR resistance to approximate lux using calibration constants."""
    return (LDR_A_CONST / resistance) ** (1.0 / LDR_B_CONST)

def read_lux():
    """
    Reads the photoresistor and returns approximate illuminance in lux.
    Returns 0.0 in darkness.
    """
    raw        = _read_avg(_ldr_adc)
    voltage    = _adc_to_voltage(raw)
    resistance = _ldr_resistance(voltage)
    return round(_resistance_to_lux(resistance), 2)

def sun_is_out():
    """Returns True if current lux reading is above the sunlight threshold."""
    return read_lux() >= LDR_SUNLIGHT_LUX


# ── Pressure Sensor (Storage Tank Volume) ────────────────────────────────────

class PressureSensor:
    """
    Pressure/weight sensor wrapper using local hx711.py driver.
    """

    def __init__(self):
        self._offset = None
        self._smoothed_kg = 0.0
        self._hx = None

        self._setup_hx711()

    def _setup_hx711(self):
        try:
            from hx711 import HX711
        except ImportError:
            raise RuntimeError("Local hx711.py driver is required for pressure sensor support")

        self._hx = HX711(PRESSURE_DATA_PIN, PRESSURE_CLOCK_PIN, channel=HX711.CHANNEL_A_128)

        # One-time tare at startup, matching the corrected acquisition flow.
        time.sleep(3)
        tare_samples = [self._median_raw() for _ in range(PRESSURE_TARE_SAMPLES)]
        self._offset = float(sum(tare_samples) / PRESSURE_TARE_SAMPLES)
        self._smoothed_kg = self._raw_to_kg(self._median_raw())

    def _read_raw_once(self):
        time.sleep(PRESSURE_SAMPLE_DELAY_S)
        if self._hx is None:
            raise RuntimeError("HX711 channel not initialized")
        return self._hx.read()

    def _median_raw(self, n=PRESSURE_SAMPLE_COUNT):
        samples = [self._read_raw_once() for _ in range(n)]
        samples.sort()
        return samples[n // 2]

    def _raw_to_kg(self, raw):
        return (raw - self._offset) / PRESSURE_CALIBRATION_FACTOR

    def _read_volume_hx711_litres(self):
        if self._offset is None:
            raise RuntimeError("HX711 tare offset not initialized")

        raw = self._median_raw()
        weight_kg = self._raw_to_kg(raw)

        # Exponential moving average for stable live values.
        self._smoothed_kg = (
            PRESSURE_EMA_ALPHA * weight_kg
            + (1.0 - PRESSURE_EMA_ALPHA) * self._smoothed_kg
        )

        # Correct slow offset drift only when the tank appears near zero.
        if abs(self._smoothed_kg) < PRESSURE_DRIFT_THRESHOLD_KG:
            self._offset = (
                (1.0 - PRESSURE_DRIFT_ALPHA) * self._offset
                + PRESSURE_DRIFT_ALPHA * raw
            )

        kg = 0.0 if abs(self._smoothed_kg) < PRESSURE_DEADBAND_KG else self._smoothed_kg
        litres = max(0.0, min(STORAGE_TANK_MAX_VOLUME_L, kg))
        return round(litres, 2)

    def read_volume_litres(self):
        return self._read_volume_hx711_litres()


_pressure_sensor = PressureSensor()

def read_storage_volume_litres():
    """
    Reads the pressure sensor and converts to volume in litres.
    Uses HX711 weight conversion.
    Water density is assumed 1 kg/L.
    """
    return _pressure_sensor.read_volume_litres()

def read_storage_fill_fraction():
    """Returns storage tank fill level as 0.0 (empty) to 1.0 (full)."""
    return read_storage_volume_litres() / STORAGE_TANK_MAX_VOLUME_L