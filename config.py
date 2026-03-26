# config.py
# ─────────────────────────────────────────────────────────────────────────────
# All user-configurable settings live here.
# Edit this file to match your hardware setup and preferences.
# ─────────────────────────────────────────────────────────────────────────────

# ── Location (for weather API) ────────────────────────────────────────────────
# Find your coordinates at: https://www.latlong.net/
LATITUDE  = 43.653225   # Example: London
LONGITUDE = -79.383186

# ── GPIO Pin Assignments ──────────────────────────────────────────────────────

# Stepper motor — single valve between PVT model tank and storage tank
MOTOR_DIR_PIN  = 16   # GPIO16 — direction control
MOTOR_STEP_PIN = 17   # GPIO17 — step pulse

# Storage tank thermistor — 10K Precision Epoxy Thermistor
THERMISTOR_STORAGE_PIN = 27   # GPIO27 (ADC1)

# PVT tank thermistor — same type, monitors hot water in PVT model tank
THERMISTOR_PVT_PIN = 28       # GPIO28 (ADC2)

# Photoresistor (LDR) — analog ADC pin
PHOTORESISTOR_PIN = 26        # GPIO26 (ADC0)

# LED — signals that water would be heated in this state (stands in for heater)
LED_PIN = 15                  # GPIO15

# Pressure sensor (HX711 load cell amplifier) — storage tank
# DATA and CLOCK follow the corrected hardware wiring.
PRESSURE_DATA_PIN  = 3         # GPIO3 (HX711 DOUT)
PRESSURE_CLOCK_PIN = 2         # GPIO2 (HX711 SCK)

# ── Stepper Motor Parameters ──────────────────────────────────────────────────
MOTOR_STEPS_PER_REV  = 500     # Steps for one full revolution
MOTOR_START_DELAY_US = 8000    # Starting pulse delay in microseconds (slow start)
MOTOR_RUN_DELAY_US   = 2000    # Running pulse delay in microseconds (full speed)
MOTOR_RAMP_STEPS     = 40      # Steps over which to ramp up to full speed
MOTOR_MOVE_ANGLE     = 90      # Degrees to rotate to open/close the valve
MOTOR_OPEN_DIRECTION = True    # True = open direction; False = reversed

# ── Thermistor Parameters (10K Precision Epoxy Thermistor) ───────────────────
# Both thermistors are the same type and share these parameters
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
STORAGE_TANK_MAX_VOLUME_L = 0.539   # Litres — physical capacity of storage tank
STORAGE_REFILL_THRESHOLD  = 0.80    # Print alert when storage drops below 80%

# Pressure sensor calibration (HX711)
# CALIBRATION_FACTOR converts raw HX711 counts into kilograms.
# 1 kg of water is assumed to be approximately 1 litre.
PRESSURE_CALIBRATION_FACTOR = 434713.0
PRESSURE_SAMPLE_COUNT       = 9        # Median window size (odd number)
PRESSURE_SAMPLE_DELAY_S     = 0.005    # Delay between raw HX711 reads
PRESSURE_TARE_SAMPLES       = 25
PRESSURE_EMA_ALPHA          = 0.7      # Live reading smoothing
PRESSURE_DRIFT_ALPHA        = 0.001    # Zero-point drift correction
PRESSURE_DRIFT_THRESHOLD_KG = 0.0002     # Drift-correct only near zero
PRESSURE_DEADBAND_KG        = 0.005    # Snap tiny values to zero

# ── Temperature Thresholds (°C) ───────────────────────────────────────────────
TEMP_PVT_READY       = 60.0   # PVT tank temp required before valve opens
TEMP_STORAGE_TARGET  = 60.0   # Desired storage tank temperature
TEMP_STORAGE_MINIMUM = 50.0   # Absolute minimum — LED on below this
TEMP_STORAGE_LED_ON  = 52.0   # Turn LED on at this temp (hysteresis lower bound)
TEMP_STORAGE_LED_OFF = 60.0   # Turn LED off once storage reaches this temp
TEMP_FREEZE_PROTECTION = 4.0  # If either sensor reads below this, close valve

# ── Weather / Timing Parameters ───────────────────────────────────────────────
PVT_HEAT_TIME_HOURS      = 1.0   # Expected hours for water to heat in PVT

# ── Control Loop ──────────────────────────────────────────────────────────────
TESTING_MODE = True         # True = use CUSTOM_DATA packets instead of real sensors
CONTROL_LOOP_INTERVAL_S = 5     # Run the main decision loop every 30 seconds