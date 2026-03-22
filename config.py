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

# Stepper motor — single valve between PVT model tank and storage tank
MOTOR_DIR_PIN  = 16   # GPIO16 — direction control
MOTOR_STEP_PIN = 17   # GPIO17 — step pulse

# Thermistor — 10K Precision Epoxy Thermistor, analog ADC pin
THERMISTOR_PIN = 27   # GPIO27 (ADC1)

# Photoresistor (LDR) — analog ADC pin
PHOTORESISTOR_PIN = 26  # GPIO26 (ADC0)

# LED — signals that water would be heated in this state (stands in for heater)
LED_PIN = 15          # GPIO15

# Pressure sensor — storage tank (analog, voltage proportional to pressure)
PRESSURE_PIN = 28     # GPIO28 (ADC2)

# ── Stepper Motor Parameters ──────────────────────────────────────────────────
MOTOR_STEPS_PER_REV  = 500     # Steps for one full revolution
MOTOR_START_DELAY_US = 8000    # Starting pulse delay in microseconds (slow start)
MOTOR_RUN_DELAY_US   = 2000    # Running pulse delay in microseconds (full speed)
MOTOR_RAMP_STEPS     = 40      # Steps over which to ramp up to full speed
MOTOR_MOVE_ANGLE     = 90      # Degrees to rotate to open/close the valve
MOTOR_OPEN_DIRECTION = True    # True = open direction; False = reversed

# ── Thermistor Parameters (10K Precision Epoxy Thermistor) ───────────────────
THERM_NOMINAL_RESISTANCE = 10000.0   # Resistance at nominal temperature (Ohms)
THERM_NOMINAL_TEMP_C     = 25.0      # Nominal temperature (°C)
THERM_B_COEFFICIENT      = 3820.0    # B coefficient from datasheet
THERM_SERIES_RESISTOR    = 10000.0   # Series resistor in voltage divider (Ohms)
THERM_OFFSET             = -1.0      # Calibration offset in °C — tune after testing

# ── Photoresistor Parameters ──────────────────────────────────────────────────
LDR_FIXED_RESISTOR = 10000.0   # Series resistor in voltage divider (Ohms)
LDR_A_CONST        = 500000.0  # Lux calibration constant A
LDR_B_CONST        = 1.4       # Lux calibration constant B
LDR_SUNLIGHT_LUX   = 1000.0    # Lux above which sun is considered out
LDR_BRIGHT_SUN_LUX = 5000.0    # Lux for strong direct sunlight

# ── Tank & System Parameters ──────────────────────────────────────────────────
STORAGE_TANK_MAX_VOLUME_L    = 200.0   # Litres — physical capacity of storage tank
STORAGE_REFILL_THRESHOLD     = 0.80    # Print alert when storage drops below 80%

# Pressure sensor calibration
# Measure output voltage with empty and full tank, set values below.
PRESSURE_VOLTAGE_AT_EMPTY = 0.5   # Volts at empty
PRESSURE_VOLTAGE_AT_FULL  = 3.0   # Volts at full

# ── Temperature Thresholds (°C) ───────────────────────────────────────────────
TEMP_PVT_READY      = 60.0   # PVT tank temp that triggers storage fill
TEMP_STORAGE_TARGET = 60.0   # Desired storage tank temperature
TEMP_STORAGE_MINIMUM = 50.0  # Absolute minimum — LED on below this
TEMP_STORAGE_LED_ON  = 52.0  # Turn LED on at this temp (hysteresis lower bound)
TEMP_STORAGE_LED_OFF = 60.0  # Turn LED off once storage reaches this temp
TEMP_FREEZE_PROTECTION = 4.0 # If sensor reads below this, close valve immediately

# ── Weather / Timing Parameters ───────────────────────────────────────────────
WEATHER_FETCH_INTERVAL_S = 900   # Fetch weather every 15 minutes (seconds)
PVT_HEAT_TIME_HOURS      = 1.0   # Expected hours for water to heat in PVT

# ── Control Loop ──────────────────────────────────────────────────────────────
CONTROL_LOOP_INTERVAL_S = 30     # Run the main decision loop every 30 seconds
