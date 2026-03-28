# custom_data.py
# ─────────────────────────────────────────────────────────────────────────────
# Custom data ingestion cache for testing mode.
# Receives sensor snapshots over USB serial from custom_data_server.py
# running on the laptop.
#
# Expected serial payload format (JSON after CUSTOM_DATA prefix):
# {
#   "tank_capacity_pct": 75,
#   "solar_lux": 25000,
#   "pvt_temp_c": 62.5,
#   "tank_temp_c": 51.2,
#   "next_hour_solar_available": true
# }
#
# FIX: sun_is_out was incorrectly derived from forecast_ok rather than lux.
# sun_is_out represents the CURRENT physical light level (what the photoresistor
# would read). sun_forecast_ok represents what is EXPECTED in the next hour.
# These are two separate signals and must not be conflated — Case 1 requires
# BOTH to be true before opening the valve.
# ─────────────────────────────────────────────────────────────────────────────

import time
from config import LDR_SUNLIGHT_LUX, STORAGE_TANK_MAX_VOLUME_L, TEMP_PVT_READY

_cache = {
    "snapshot": None,
    "updated_at": 0,
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return None


def ingest_serial_payload(payload):
    """Parses and caches one custom-data payload. Returns True on success."""
    if not isinstance(payload, dict):
        return False

    try:
        tank_capacity_pct = float(payload.get("tank_capacity_pct", 0.0))
        solar_lux         = float(payload.get("solar_lux", 0.0))
        pvt_temp          = float(payload.get("pvt_temp_c", 0.0))
        storage_temp      = float(payload.get("tank_temp_c", 0.0))
        forecast_ok       = _to_bool(payload.get("next_hour_solar_available", None))
    except Exception as e:
        print(f"  Custom data parse failed: {e}")
        return False

    storage_frac  = _clamp(tank_capacity_pct / 100.0, 0.0, 1.0)
    storage_vol_l = round(storage_frac * STORAGE_TANK_MAX_VOLUME_L, 3)
    pvt_ready     = pvt_temp >= TEMP_PVT_READY

    # FIX: sun_is_out reflects the CURRENT light level from solar_lux,
    # matching what the physical photoresistor would report.
    # forecast_ok is kept separate as sun_forecast_ok.
    # Previously sun_is_out = bool(forecast_ok) when forecast_ok was not None,
    # which meant a true forecast would incorrectly report the sun as currently
    # out even in darkness — breaking the combined Case 1 valve condition.
    sun_is_out = solar_lux >= LDR_SUNLIGHT_LUX

    _cache["snapshot"] = {
        "storage_temp":    round(storage_temp, 2),
        "pvt_temp":        round(pvt_temp, 2),
        "pvt_ready":       pvt_ready,
        "lux":             round(solar_lux, 2),
        "sun_is_out":      sun_is_out,
        "storage_vol_l":   storage_vol_l,
        "storage_frac":    storage_frac,
        "sun_forecast_ok": forecast_ok,
    }
    _cache["updated_at"] = time.time()
    return True


def get_latest_snapshot():
    """Returns latest cached custom snapshot, or None if never received."""
    return _cache["snapshot"]


def get_updated_at():
    """Returns epoch timestamp of latest custom snapshot update."""
    return _cache["updated_at"]
