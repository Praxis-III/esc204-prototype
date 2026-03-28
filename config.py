# config.py
# ─────────────────────────────────────────────────────────────────────────────
# All user-configurable settings live here.
# Edit this file to match your hardware setup and preferences.
# ─────────────────────────────────────────────────────────────────────────────

# ── Location (for weather API) ────────────────────────────────────────────────
# Find your coordinates at: https://www.latlong.net/
LATITUDE  = 43.653225   # Toronto, ON
LONGITUDE = -79.383186

# ── GPIO Pin Assignments ──────────────────────────────────────────────────────

# DC pump relay — JAVTOP JT280T via active-low relay module
PUMP_RELAY_PIN = 15   # GPIO15 — relay signal (S) pin

# Storage tank thermistor — 10K Precision Epoxy Thermistor
THERMISTOR_STORAGE_PIN = 27   # GPIO27 (ADC1)

# PVT tank thermistor — same type, monitors hot water in PVT model tank
THERMISTOR_PVT_PIN = 28       # GPIO28 (ADC2)

# Photoresistor (LDR) — analog ADC pin
PHOTORESISTOR_PIN = 26        # GPIO26 (ADC0)

# LED — models electric heater (signals water would be heated in this state)
LED_PIN = 16                  # GPIO16

# Pressure sensor (HX711 load cell amplifier) — storage tank
PRESSURE_DATA_PIN  = 3        # GPIO3  (HX711 DOUT)
PRESSURE_CLOCK_PIN = 2        # GPIO2  (HX711 SCK)

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
# 1 kg of water = 1 litre assumed.
PRESSURE_CALIBRATION_FACTOR = 434713.0
PRESSURE_SAMPLE_COUNT       = 9        # Median window size (must be odd)
PRESSURE_SAMPLE_DELAY_S     = 0.005    # Delay between raw HX711 reads
PRESSURE_TARE_SAMPLES       = 25       # Samples averaged for tare at startup
PRESSURE_EMA_ALPHA          = 0.7      # Live reading smoothing factor
PRESSURE_DRIFT_ALPHA        = 0.001    # Zero-point drift correction rate
PRESSURE_DRIFT_THRESHOLD_KG = 0.0002   # Drift-correct only when near zero
PRESSURE_DEADBAND_KG        = 0.005    # Snap tiny values to zero

# ── Temperature Thresholds (°C) ───────────────────────────────────────────────
TEMP_PVT_READY       = 60.0   # PVT tank temp required before pump starts (ideal)
TEMP_PVT_SOFT        = 55.0   # Soft PVT threshold — used only in specific truth
                               # table rows where 60°C is not strictly required
                               # (e.g. sun is out and tank is critically low).
                               # Never used as the primary ready condition.
TEMP_STORAGE_TARGET  = 60.0   # Desired storage tank temperature
TEMP_STORAGE_MINIMUM = 50.0   # Absolute minimum storage temperature
TEMP_STORAGE_LED_ON  = 52.0   # Turn LED on at this temp (hysteresis lower bound)
TEMP_STORAGE_LED_OFF = 60.0   # Turn LED off once storage reaches this temp
TEMP_FREEZE_PROTECTION = 4.0  # If either sensor reads below this, stop pump

# ── Weather / Timing Parameters ───────────────────────────────────────────────
PVT_HEAT_TIME_HOURS = 1.0     # Expected hours for water to heat in PVT

# ── Demand Detection ──────────────────────────────────────────────────────────
# To detect active water consumption from the storage tank, the controller
# compares the current volume to a rolling buffer of recent readings.
# If volume has dropped by more than PRESSURE_DEMAND_DEADBAND_L over the
# buffer window, active demand is flagged and waiting-for-sun logic is bypassed.
PRESSURE_DEMAND_DEADBAND_L  = 0.005  # Minimum volume drop (L) to count as demand
PRESSURE_DEMAND_WINDOW_S    = 30     # Seconds of history to check for demand drop

# ── LDR Trend Forecast ────────────────────────────────────────────────────────
# When WiFi forecast is unavailable, ldr_trend.py uses a rolling history of
# lux readings to predict whether the sun will persist.
LDR_TREND_WINDOW_S      = 600   # Rolling window length in seconds (10 min).
                                 # Long enough to ignore passing clouds.
LDR_TREND_DECLINE_RATIO = 0.6   # If latest lux < this fraction of window
                                 # average, trend is considered declining.
LDR_FORECAST_STALE_S    = 86400 # WiFi forecast older than this (1 day) is
                                 # considered stale — LDR trend takes over fully.

# ── Control Loop ──────────────────────────────────────────────────────────────
# TESTING_MODE = True  → controller reads from custom_data serial packets
#                         instead of physical sensors. Used for bench testing.
# TESTING_MODE = False → controller reads from all physical hardware.
TESTING_MODE            = True
CONTROL_LOOP_INTERVAL_S = 5    # Seconds between control loop cycles.
                                # NOTE: Ideally the storage tank volume should
                                # be polled at ~1s intervals to catch rapid
                                # demand changes described in the truth table.
                                # The current single-loop architecture reads
                                # all sensors at the same interval. A future
                                # iteration could split volume polling into a
                                # dedicated fast inner loop while keeping slow
                                # sensor reads (temp, weather) at longer intervals.
