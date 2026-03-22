# ============================================================
# HARDWARE SETUP CHECKLIST — complete before first real run
# ============================================================
# [ ] 1. Set WIFI_SSID and WIFI_PASSWORD
# [ ] 2. Set LATITUDE and LONGITUDE for your location
# [ ] 3. Check GPIO pin numbers match your actual wiring
# [ ] 4. Run sensors.scan_sensors() in Thonny REPL
#         and paste the 4 DS18B20 addresses below
# [ ] 5. Calibrate pressure sensor — measure voltage at
#         empty and full tank, update PRESSURE_VOLTAGE_AT_EMPTY
#         and PRESSURE_VOLTAGE_AT_FULL
# [ ] 6. Re-upload config.py after all changes
# ============================================================
import board

# config.py
# ─────────────────────────────────────────────────────────────────────────────
# All user-configurable settings live here.
# Edit this file to match your hardware setup and preferences.
# ─────────────────────────────────────────────────────────────────────────────

# ── Wi-Fi ─────────────────────────────────────────────────────────────────────
WIFI_SSID     = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# ── Location (for weather API) ────────────────────────────────────────────────
# Find your coordinates at: https://www.latlong.net/
LATITUDE  = 51.5074   # Example: London
LONGITUDE = -0.1278

# ── GPIO Pin Assignments ──────────────────────────────────────────────────────
# Temperature sensors (DS18B20 — all share one data wire via 1-Wire protocol)
# You will use the sensor addresses to distinguish them (see sensors.py)
ONEWIRE_PIN = 4         # GPIO4 — connect all DS18B20 data lines here

# Photoresistor (LDR) — connect via a voltage divider to an ADC pin
PHOTORESISTOR_PIN = board.A0  # GPIO26 (ADC0)

# Valve motor — supply tank (controls flow from supply tank into PVT)
MOTOR_SUPPLY_PIN = 14   # GPIO14

# Valve motor — storage tank (controls flow from PVT into storage tank)
MOTOR_STORAGE_PIN = 15  # GPIO15

# Electric heater relay (HIGH = heater ON)
HEATER_PIN = 16         # GPIO16

# Pressure sensor — storage tank (analog, gives voltage proportional to pressure)
PRESSURE_PIN = 27       # GPIO27 (ADC1)

# ── Tank & System Parameters ──────────────────────────────────────────────────
STORAGE_TANK_MAX_VOLUME_L  = 200.0   # Litres — physical capacity of storage tank
SUPPLY_TANK_MAX_VOLUME_L   = 300.0   # Litres — physical capacity of supply tank
SUPPLY_TANK_REFILL_THRESHOLD = 0.80  # Refill supply tank when it drops below 80%

# Pressure sensor calibration
# You need to measure voltage at 0L and at max volume, then set these values.
PRESSURE_VOLTAGE_AT_EMPTY = 0.5   # Volts at 0 kg (empty)
PRESSURE_VOLTAGE_AT_FULL  = 3.0   # Volts at max_volume kg (full)

# ── Temperature Thresholds (°C) ───────────────────────────────────────────────
TEMP_PVT_READY           = 60.0   # PVT output temp that triggers storage fill
TEMP_STORAGE_TARGET      = 60.0   # Desired storage tank temperature
TEMP_STORAGE_MINIMUM     = 50.0   # Absolute minimum — heater kicks in below this
TEMP_STORAGE_HEATER_ON   = 52.0   # Turn heater on at this temp (hysteresis band)
TEMP_STORAGE_HEATER_OFF  = 60.0   # Turn heater off once storage reaches this temp
TEMP_FREEZE_PROTECTION   = 4.0    # If any sensor reads below this, purge pipes

# ── Photoresistor Thresholds ──────────────────────────────────────────────────
# ADC returns 0–65535. Tune these based on your LDR and voltage divider.
LDR_SUNLIGHT_THRESHOLD   = 40000  # Above this raw ADC value = sun is out
LDR_BRIGHT_SUN_THRESHOLD = 55000  # Above this = very strong direct sunlight

# ── Weather / Timing Parameters ───────────────────────────────────────────────
WEATHER_FETCH_INTERVAL_S   = 900   # Fetch weather every 15 minutes (seconds)
# Time (in hours) we expect water to need to heat up in the PVT.
# If the sun is forecast to stay out for this long, it's safe to start flow.
PVT_HEAT_TIME_HOURS        = 1.0

# ── Control Loop ─────────────────────────────────────────────────────────────
CONTROL_LOOP_INTERVAL_S    = 30    # Run the main decision loop every 30 seconds

# ── Sensor Addresses ─────────────────────────────────────────────────────────
# After running sensors.py scan, paste the printed addresses here.
# Format: bytearray of 8 bytes. The scan will print them ready to copy-paste.
DS18B20_STORAGE_TOP    = None   # e.g. bytearray(b'\x28\xff\x...')
DS18B20_STORAGE_MID    = None
DS18B20_STORAGE_BOTTOM = None
DS18B20_PVT            = None