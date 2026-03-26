import time
from config import (
    PRESSURE_DATA_PIN, PRESSURE_CLOCK_PIN,
    PRESSURE_CALIBRATION_FACTOR,
    PRESSURE_SAMPLE_COUNT, PRESSURE_SAMPLE_DELAY_S,
    PRESSURE_TARE_SAMPLES,
    PRESSURE_EMA_ALPHA, PRESSURE_DRIFT_ALPHA,
    PRESSURE_DRIFT_THRESHOLD_KG, PRESSURE_DEADBAND_KG,
    STORAGE_TANK_MAX_VOLUME_L,
)


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
        raw = self._hx.read()
        return raw

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
        self._smoothed_kg = abs(
            PRESSURE_EMA_ALPHA * weight_kg
            + (1.0 - PRESSURE_EMA_ALPHA) * self._smoothed_kg
        )

        print(self._smoothed_kg)

        # # Correct slow offset drift only when the tank appears near zero.
        # if abs(self._smoothed_kg) < PRESSURE_DRIFT_THRESHOLD_KG:
        #     self._offset = (
        #         (1.0 - PRESSURE_DRIFT_ALPHA) * self._offset
        #         + PRESSURE_DRIFT_ALPHA * raw
        #     )

        kg = 0.0 if abs(self._smoothed_kg) < PRESSURE_DEADBAND_KG else self._smoothed_kg
        litres = max(0.0, min(STORAGE_TANK_MAX_VOLUME_L, kg))
        print(str(litres) + " mL")
        return round(litres, 2)

    def read_volume_litres(self):
        return self._read_volume_hx711_litres()