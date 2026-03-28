# sensors.py
# ─────────────────────────────────────────────────────────────────────────────
# Handles all sensor reading:
#   - Storage tank thermistor (10K Precision Epoxy, GPIO27)
#   - PVT tank thermistor    (same type, GPIO28)
#   - Photoresistor / LDR    (lux conversion, GPIO26)
#   - Pressure sensor        (HX711 load cell, GPIO2/GPIO3)
#
# Both thermistors are identical in type and share calibration constants
# from config.py. They are read independently via separate ADC pins.
#
# All analog sensors use MicroPython's machine.ADC (16-bit, 3.3V reference).
#
# FIX: PressureSensor is lazy-initialised on first use rather than at module
# level. This prevents the HX711 tare sequence (3s sleep + 25 samples) from
# running on import, which would crash the system if the HX711 is not connected.
# ─────────────────────────────────────────────────────────────────────────────

import machine
import math
from config import (
    THERMISTOR_STORAGE_PIN, THERMISTOR_PVT_PIN,
    PHOTORESISTOR_PIN,
    THERM_NOMINAL_RESISTANCE, THERM_NOMINAL_TEMP_C,
    THERM_B_COEFFICIENT, THERM_SERIES_RESISTOR, THERM_OFFSET,
    LDR_FIXED_RESISTOR, LDR_A_CONST, LDR_B_CONST,
    LDR_SUNLIGHT_LUX,
    STORAGE_TANK_MAX_VOLUME_L,
)

# ── ADC Setup ─────────────────────────────────────────────────────────────────
_therm_storage_adc = machine.ADC(THERMISTOR_STORAGE_PIN)
_therm_pvt_adc     = machine.ADC(THERMISTOR_PVT_PIN)
_ldr_adc           = machine.ADC(PHOTORESISTOR_PIN)

_ADC_MAX = 65535
_VREF    = 3.3

# ── Lazy pressure sensor ──────────────────────────────────────────────────────
# _pressure_sensor is None until first call to read_storage_volume_litres().
# This avoids the HX711 tare running at import time.
_pressure_sensor = None

def _get_pressure_sensor():
    """
    Returns the PressureSensor instance, initialising it on first call.
    Separating initialisation from import means the tare sequence only runs
    when volume is actually needed, not the moment sensors.py is imported.
    """
    global _pressure_sensor
    if _pressure_sensor is None:
        from pressure_sensor import PressureSensor
        _pressure_sensor = PressureSensor()
    return _pressure_sensor


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
    Divider: Vref → Rs → ADC node → R_therm → GND  (thermistor on bottom)
    R_therm = Rs * V / (Vref - V)
    """
    if voltage >= _VREF or voltage <= 0:
        return None
    return THERM_SERIES_RESISTOR * voltage / (_VREF - voltage)

def _resistance_to_temp_c(resistance):
    """
    Converts thermistor resistance to °C using Steinhart-Hart B-parameter eq:
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
    """
    Converts LDR voltage divider output to LDR resistance.
    Divider: Vref → LDR → ADC node → R_fixed → GND
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
    Returns near-zero in complete darkness.
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
    Reads the HX711 pressure/weight sensor and returns volume in litres.
    Initialises the sensor on first call (triggers tare sequence).
    Water density assumed 1 kg/L.
    """
    return _get_pressure_sensor().read_volume_litres()

def read_storage_fill_fraction():
    """Returns storage tank fill level as 0.0 (empty) to 1.0 (full)."""
    return read_storage_volume_litres() / STORAGE_TANK_MAX_VOLUME_L
