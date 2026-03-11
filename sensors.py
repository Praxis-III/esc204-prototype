# sensors.py
# ─────────────────────────────────────────────────────────────────────────────
# Handles all sensor reading:
#   - DS18B20 temperature sensors (1-Wire)
#   - Photoresistor / LDR (analog ADC)
#   - Pressure sensor (analog ADC → volume in litres)
# ─────────────────────────────────────────────────────────────────────────────

import machine
import onewire
import ds18x20
import time
from config import (
    ONEWIRE_PIN, PHOTORESISTOR_PIN, PRESSURE_PIN,
    DS18B20_STORAGE_TOP, DS18B20_STORAGE_MID, DS18B20_STORAGE_BOTTOM, DS18B20_PVT,
    PRESSURE_VOLTAGE_AT_EMPTY, PRESSURE_VOLTAGE_AT_FULL,
    STORAGE_TANK_MAX_VOLUME_L
)

# ── 1-Wire / DS18B20 Setup ────────────────────────────────────────────────────
_ow_pin  = machine.Pin(ONEWIRE_PIN)
_ow_bus  = onewire.OneWire(_ow_pin)
_ds      = ds18x20.DS18X20(_ow_bus)

# ── ADC Setup ─────────────────────────────────────────────────────────────────
_ldr_adc      = machine.ADC(PHOTORESISTOR_PIN)
_pressure_adc = machine.ADC(PRESSURE_PIN)

# Pico W ADC reference voltage is 3.3V, 16-bit (0–65535)
_ADC_MAX   = 65535
_VREF      = 3.3


def scan_sensors():
    """
    Scans the 1-Wire bus and prints all found sensor addresses.
    Run this ONCE when you first set up hardware to identify which address
    belongs to which physical sensor (put them in warm/cold water to tell apart).
    Then paste the addresses into config.py.
    """
    print("Scanning 1-Wire bus for DS18B20 sensors...")
    roms = _ds.scan()
    if not roms:
        print("  No sensors found! Check wiring and pull-up resistor (4.7kΩ).")
        return
    print(f"  Found {len(roms)} sensor(s):")
    for i, rom in enumerate(roms):
        print(f"    Sensor {i}: bytearray({bytes(rom)})")
    print("\nCopy these into config.py as DS18B20_STORAGE_TOP, _MID, _BOTTOM, _PVT")


def _read_temp_c(rom_address):
    """
    Read temperature from a specific DS18B20 sensor by its ROM address.
    Returns temperature in °C, or None on failure.
    """
    if rom_address is None:
        return None
    try:
        _ds.convert_temp()
        time.sleep_ms(750)  # DS18B20 needs ~750ms to convert
        return _ds.read_temp(rom_address)
    except Exception as e:
        print(f"  Temp sensor read error: {e}")
        return None


def read_storage_temps():
    """
    Returns a dict with storage tank temperatures:
    { 'top': float|None, 'mid': float|None, 'bottom': float|None }
    """
    # Trigger all sensors to convert at once (more efficient than one-by-one)
    try:
        _ds.convert_temp()
        time.sleep_ms(750)
    except Exception as e:
        print(f"  DS18B20 convert error: {e}")
        return {'top': None, 'mid': None, 'bottom': None}

    def safe_read(rom):
        if rom is None:
            return None
        try:
            return _ds.read_temp(rom)
        except Exception as e:
            print(f"  Read error for {rom}: {e}")
            return None

    return {
        'top':    safe_read(DS18B20_STORAGE_TOP),
        'mid':    safe_read(DS18B20_STORAGE_MID),
        'bottom': safe_read(DS18B20_STORAGE_BOTTOM),
    }


def read_pvt_temp():
    """Returns PVT panel temperature in °C, or None on failure."""
    try:
        _ds.convert_temp()
        time.sleep_ms(750)
        if DS18B20_PVT is None:
            return None
        return _ds.read_temp(DS18B20_PVT)
    except Exception as e:
        print(f"  PVT temp read error: {e}")
        return None


def read_ldr_raw():
    """
    Returns the raw ADC value from the photoresistor (0–65535).
    Higher = more light (assuming LDR in a pull-down voltage divider config).
    """
    return _ldr_adc.read_u16()


def read_ldr_percent():
    """Returns light level as 0–100% (100% = brightest)."""
    return round((read_ldr_raw() / _ADC_MAX) * 100, 1)


def read_storage_volume_litres():
    """
    Reads the pressure sensor and converts to volume in litres.
    Uses the calibration values in config.py.
    Assumes water density = 1 kg/L.
    """
    raw   = _pressure_adc.read_u16()
    volts = (raw / _ADC_MAX) * _VREF

    # Linear interpolation between empty and full calibration points
    volt_range = PRESSURE_VOLTAGE_AT_FULL - PRESSURE_VOLTAGE_AT_EMPTY
    if volt_range == 0:
        return 0.0

    fraction = (volts - PRESSURE_VOLTAGE_AT_EMPTY) / volt_range
    fraction = max(0.0, min(1.0, fraction))   # Clamp to 0–1

    return round(fraction * STORAGE_TANK_MAX_VOLUME_L, 2)


def read_storage_fill_fraction():
    """Returns storage tank fill level as 0.0–1.0."""
    return read_storage_volume_litres() / STORAGE_TANK_MAX_VOLUME_L


def estimate_mixed_temp(temp_top, temp_bottom, volume_top_l, volume_bottom_l):
    """
    Estimates the equilibrium temperature when two water volumes mix.
    Uses a simple energy balance (mass * temp weighted average).
    Water density assumed 1 kg/L so mass (kg) == volume (L).
    """
    if volume_top_l + volume_bottom_l == 0:
        return None
    return ((temp_top * volume_top_l) + (temp_bottom * volume_bottom_l)) / (volume_top_l + volume_bottom_l)
