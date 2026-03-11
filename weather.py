# weather.py
# ─────────────────────────────────────────────────────────────────────────────
# Fetches weather forecast from Open-Meteo API (free, no API key required).
# Parses hourly cloud cover and precipitation to estimate sunshine hours ahead.
# ─────────────────────────────────────────────────────────────────────────────

import urequests
import time
from config import LATITUDE, LONGITUDE, PVT_HEAT_TIME_HOURS

# Open-Meteo API — requests hourly cloud cover and precipitation for next 24h
# cloudcover: 0 (clear) to 100 (fully overcast)
# precipitation: mm/hour
_API_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LATITUDE}&longitude={LONGITUDE}"
    "&hourly=cloudcover,precipitation,temperature_2m"
    "&forecast_days=1"
    "&timezone=auto"
)

# Cache the last successful fetch so we don't hammer the API
_cache = {
    'data':       None,
    'fetched_at': 0,     # time.time() of last fetch
}


def fetch_forecast():
    """
    Fetches hourly weather forecast and caches it.
    Returns a dict with parsed forecast, or None on failure.
    """
    try:
        print("Fetching weather forecast from Open-Meteo...")
        r = urequests.get(_API_URL, timeout=10)
        if r.status_code != 200:
            print(f"  Weather API returned status {r.status_code}")
            r.close()
            return None

        raw = r.json()
        r.close()

        hourly = raw.get('hourly', {})
        times       = hourly.get('time', [])
        cloudcover  = hourly.get('cloudcover', [])
        precip      = hourly.get('precipitation', [])
        temps       = hourly.get('temperature_2m', [])

        parsed = []
        for i in range(len(times)):
            parsed.append({
                'time':        times[i],
                'cloudcover':  cloudcover[i] if i < len(cloudcover) else 100,
                'precip_mm':   precip[i]     if i < len(precip)     else 0,
                'air_temp_c':  temps[i]      if i < len(temps)      else None,
            })

        _cache['data']       = parsed
        _cache['fetched_at'] = time.time()
        print(f"  Weather fetched OK. {len(parsed)} hourly entries.")
        return parsed

    except Exception as e:
        print(f"  Weather fetch FAILED: {e}")
        return None


def get_forecast():
    """Returns cached forecast data (or None if never fetched)."""
    return _cache['data']


def sun_will_last_long_enough(hours_needed=None):
    """
    Returns True if the forecast shows enough sunshine ahead to justify
    starting water flow through the PVT.

    Logic:
    - Looks at the next `hours_needed` hours of forecast.
    - If average cloud cover < 50% AND no significant rain, returns True.
    - If no forecast data is available, returns None (unknown).
    """
    if hours_needed is None:
        hours_needed = PVT_HEAT_TIME_HOURS

    data = get_forecast()
    if data is None or len(data) == 0:
        return None   # Unknown — caller should decide how to handle

    # We only look at the next N hours (each entry is 1 hour)
    window = data[:max(1, int(hours_needed))]

    avg_cloud = sum(h['cloudcover'] for h in window) / len(window)
    max_precip = max(h['precip_mm'] for h in window)

    is_sunny  = avg_cloud < 50       # Less than 50% cloud = mostly sunny
    is_dry    = max_precip < 0.5     # Less than 0.5mm/hr = no meaningful rain

    print(f"  Forecast window ({hours_needed}h): avg cloud={avg_cloud:.0f}%, max rain={max_precip:.1f}mm")
    print(f"  Sun will last: {is_sunny and is_dry}")
    return is_sunny and is_dry


def get_next_sunshine_hours():
    """
    Returns a rough count of how many of the next 12 hours are expected to be sunny.
    Useful for planning whether to pre-heat water.
    """
    data = get_forecast()
    if not data:
        return 0
    sunny_hours = sum(
        1 for h in data[:12]
        if h['cloudcover'] < 50 and h['precip_mm'] < 0.5
    )
    return sunny_hours
