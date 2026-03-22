# sensors.py
# ─────────────────────────────────────────────────────────────────────────────
# Handles all sensor reading:
#   - Thermistor (10K Precision Epoxy, Steinhart-Hart equation)
#   - Photoresistor / LDR (lux conversion)
#   - Pressure sensor (analog ADC → volume in litres)
#
# All sensors use MicroPython's machine.ADC (16-bit, 0–65535, 3.3V reference).
# ─────────────────────────────────────────────────────────────────────────────

import machine
import math
from config import (
    THERMISTOR_PIN, PHOTORESISTOR_PIN, PRESSURE_PIN,
    THERM_NOMINAL_RESISTANCE, THERM_NOMINAL_TEMP_C,
    THERM_B_COEFFICIENT, THERM_SERIES_RESISTOR, THERM_OFFSET,
    LDR_FIXED_RESISTOR, LDR_A_CONST, LDR_B_CONST,
    LDR_SUNLIGHT_LUX, LDR_BRIGHT_SUN_LUX,
    PRESSURE_VOLTAGE_AT_EMPTY, PRESSURE_VOLTAGE_AT_FULL,
    STORAGE_TANK_MAX_VOLUME_L,
)

# ── ADC Setup ─────────────────────────────────────────────────────────────────
_therm_adc    = machine.ADC(THERMISTOR_PIN)
_ldr_adc      = machine.ADC(PHOTORESISTOR_PIN)
_pressure_adc = machine.ADC(PRESSURE_PIN)

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


# ── Thermistor ────────────────────────────────────────────────────────────────

def read_temp_c():
    """
    Reads the 10K Precision Epoxy Thermistor and returns temperature in °C.
    Uses the Steinhart-Hart B-parameter equation:
        1/T = 1/T0 + (1/B) * ln(R/R0)
    Returns None if the reading is out of a plausible range.
    """
    raw = _read_avg(_therm_adc)

    if raw <= 0:
        return None

    voltage    = _adc_to_voltage(raw)
    # Voltage divider: thermistor on top, series resistor on bottom
    # R_therm = R_series / (V_ref/V_out - 1)
    resistance = THERM_SERIES_RESISTOR / (_VREF / voltage - 1)

    # Steinhart-Hart B-parameter equation
    steinhart  = resistance / THERM_NOMINAL_RESISTANCE
    steinhart  = math.log(steinhart)
    steinhart /= THERM_B_COEFFICIENT
    steinhart += 1.0 / (THERM_NOMINAL_TEMP_C + 273.15)
    temp_k     = 1.0 / steinhart
    temp_c     = temp_k - 273.15 + THERM_OFFSET

    return round(temp_c, 2)


# ── Photoresistor / LDR ───────────────────────────────────────────────────────

def _ldr_resistance(voltage):
    """Converts LDR voltage divider output to LDR resistance."""
    if voltage <= 0.001:
        return 1e9   # Effectively infinite resistance in darkness
    return LDR_FIXED_RESISTOR * (_VREF - voltage) / voltage

def _resistance_to_lux(resistance):
    """Converts LDR resistance to approximate lux using calibration constants."""
    return (LDR_A_CONST / resistance) ** (1.0 / LDR_B_CONST)

def read_lux():
    """
    Reads the photoresistor and returns approximate illuminance in lux.
    Higher lux = more light. Uses empirical calibration constants from photo.py.
    Returns 0.0 if the sensor reads no light.
    """
    raw        = _read_avg(_ldr_adc)
    voltage    = _adc_to_voltage(raw)
    resistance = _ldr_resistance(voltage)
    lux        = _resistance_to_lux(resistance)
    return round(lux, 2)

def sun_is_out():
    """Returns True if current lux reading is above the sunlight threshold."""
    return read_lux() >= LDR_SUNLIGHT_LUX

def sun_is_bright():
    """Returns True if current lux reading indicates strong direct sunlight."""
    return read_lux() >= LDR_BRIGHT_SUN_LUX


# ── Pressure Sensor (Storage Tank Volume) ────────────────────────────────────

def read_storage_volume_litres():
    """
    Reads the pressure sensor and converts to volume in litres.
    Uses linear interpolation between the two calibration voltages in config.py.
    Water density assumed 1 kg/L so mass (kg) == volume (L).
    Result is clamped to 0–max to handle sensor noise at extremes.
    """
    raw   = _read_avg(_pressure_adc)
    volts = _adc_to_voltage(raw)

    volt_range = PRESSURE_VOLTAGE_AT_FULL - PRESSURE_VOLTAGE_AT_EMPTY
    if volt_range == 0:
        return 0.0

    fraction = (volts - PRESSURE_VOLTAGE_AT_EMPTY) / volt_range
    fraction = max(0.0, min(1.0, fraction))   # Clamp to valid range

    return round(fraction * STORAGE_TANK_MAX_VOLUME_L, 2)

def read_storage_fill_fraction():
    """Returns storage tank fill level as 0.0 (empty) to 1.0 (full)."""
    return read_storage_volume_litres() / STORAGE_TANK_MAX_VOLUME_L
