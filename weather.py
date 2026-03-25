# weather.py
# ─────────────────────────────────────────────────────────────────────────────
# Receives weather forecast data over USB serial from a laptop-side script.
# Parses hourly cloud cover and precipitation to estimate sunshine hours ahead.
# ─────────────────────────────────────────────────────────────────────────────

import sys
import time
from config import PVT_HEAT_TIME_HOURS

try:
    import ujson as json
except ImportError:
    import json

try:
    import uselect
except ImportError:
    uselect = None

# Cache the last successful fetch so we don't hammer the API
_cache = {
    'data':       None,
    'daily':      None,
    'sunrise':    None,
    'sunset':     None,
    'fetched_at': 0,     # time.time() of last fetch
}

_SERIAL_PREFIX = "WEATHER "
_poller = None

if uselect is not None:
    _poller = uselect.poll()
    _poller.register(sys.stdin, uselect.POLLIN)


def _parse_hourly_payload(hourly):
    """Converts Open-Meteo hourly arrays into internal parsed format."""
    times      = hourly.get('time', [])
    cloudcover = hourly.get('cloudcover', [])
    precip     = hourly.get('precipitation', [])
    temps      = hourly.get('temperature_2m', [])

    parsed = []
    for i in range(len(times)):
        parsed.append({
            'time':        times[i],
            'cloudcover':  cloudcover[i] if i < len(cloudcover) else 100,
            'precip_mm':   precip[i]     if i < len(precip)     else 0,
            'air_temp_c':  temps[i]      if i < len(temps)      else None,
        })
    return parsed


def _ingest_serial_payload(payload):
    """
    Updates cache from decoded payload.
    Supports either:
      1) {'hourly': {...Open-Meteo arrays...}}
      2) {'parsed': [{time, cloudcover, precip_mm, air_temp_c}, ...]}
    """
    parsed = None

    daily = None
    sunrise = None
    sunset = None

    if isinstance(payload, dict):
        if 'parsed' in payload and isinstance(payload['parsed'], list):
            parsed = payload['parsed']
        elif 'hourly' in payload and isinstance(payload['hourly'], dict):
            parsed = _parse_hourly_payload(payload['hourly'])

        if 'daily' in payload and isinstance(payload['daily'], dict):
            daily = payload['daily']
            sunrise_list = daily.get('sunrise', [])
            sunset_list = daily.get('sunset', [])
            if sunrise_list:
                sunrise = sunrise_list[0]
            if sunset_list:
                sunset = sunset_list[0]

    if not parsed:
        return False

    _cache['data'] = parsed
    _cache['daily'] = daily
    _cache['sunrise'] = sunrise
    _cache['sunset'] = sunset
    _cache['fetched_at'] = time.time()
    print(f"  Weather updated from serial. {len(parsed)} hourly entries.")
    if sunrise is not None and sunset is not None:
        print(f"  Sunrise: {sunrise}  Sunset: {sunset}")
    return True


def poll_serial(max_lines=3):
    """
    Non-blocking serial poll.
    Reads up to `max_lines` lines from USB serial and ingests any WEATHER payload.
    Returns number of successfully ingested weather packets.
    """
    if _poller is None:
        return 0

    updates = 0
    for _ in range(max_lines):
        if not _poller.poll(0):
            break

        line = sys.stdin.readline()
        if not line:
            continue

        line = line.strip()
        if not line.startswith(_SERIAL_PREFIX):
            continue

        raw_json = line[len(_SERIAL_PREFIX):]
        try:
            payload = json.loads(raw_json)
            if _ingest_serial_payload(payload):
                updates += 1
        except Exception as e:
            print(f"  Weather serial parse failed: {e}")

    return updates


def fetch_forecast():
    """
    Compatibility wrapper.
    Tries to ingest forecast packets already waiting on serial.
    Returns cached parsed forecast, or None if unavailable.
    """
    updates = poll_serial(max_lines=10)
    if updates == 0:
        print("  No new serial weather packet available.")
    return _cache['data']


def wait_for_initial_forecast(timeout_s=5):
    """Waits briefly for first weather packet from serial, then returns cache."""
    start = time.time()
    while (time.time() - start) < timeout_s:
        if poll_serial(max_lines=10) > 0 and _cache['data']:
            return _cache['data']
        time.sleep(0.1)
    return _cache['data']


def get_forecast():
    """Returns cached forecast data (or None if never fetched)."""
    return _cache['data']


def get_sunrise():
    """Returns today's sunrise timestamp string from latest weather packet."""
    return _cache['sunrise']


def get_sunset():
    """Returns today's sunset timestamp string from latest weather packet."""
    return _cache['sunset']


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
