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
from config import (
    THERMISTOR_STORAGE_PIN, THERMISTOR_PVT_PIN,
    PHOTORESISTOR_PIN, PRESSURE_PIN,
    THERM_NOMINAL_RESISTANCE, THERM_NOMINAL_TEMP_C,
    THERM_B_COEFFICIENT, THERM_SERIES_RESISTOR, THERM_OFFSET,
    LDR_FIXED_RESISTOR, LDR_A_CONST, LDR_B_CONST,
    LDR_SUNLIGHT_LUX, LDR_BRIGHT_SUN_LUX,
    PRESSURE_VOLTAGE_AT_EMPTY, PRESSURE_VOLTAGE_AT_FULL,
    STORAGE_TANK_MAX_VOLUME_L,
)

# ── ADC Setup ─────────────────────────────────────────────────────────────────
_therm_storage_adc = machine.ADC(THERMISTOR_STORAGE_PIN)
_therm_pvt_adc     = machine.ADC(THERMISTOR_PVT_PIN)
_ldr_adc           = machine.ADC(PHOTORESISTOR_PIN)
_pressure_adc      = machine.ADC(PRESSURE_PIN)

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

def read_storage_volume_litres():
    """
    Reads the pressure sensor and converts to volume in litres.
    Uses linear interpolation between the two calibration voltages in config.py.
    Water density assumed 1 kg/L.
    """
    raw   = _read_avg(_pressure_adc)
    volts = _adc_to_voltage(raw)

    volt_range = PRESSURE_VOLTAGE_AT_FULL - PRESSURE_VOLTAGE_AT_EMPTY
    if volt_range == 0:
        return 0.0

    fraction = (volts - PRESSURE_VOLTAGE_AT_EMPTY) / volt_range
    fraction = max(0.0, min(1.0, fraction))
    return round(fraction * STORAGE_TANK_MAX_VOLUME_L, 2)

def read_storage_fill_fraction():
    """Returns storage tank fill level as 0.0 (empty) to 1.0 (full)."""
    return read_storage_volume_litres() / STORAGE_TANK_MAX_VOLUME_L