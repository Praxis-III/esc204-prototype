# ldr_trend.py
# ─────────────────────────────────────────────────────────────────────────────
# LDR-based solar forecast fallback.
#
# Used when the WiFi weather forecast is unavailable or stale (>24h old).
# Maintains a rolling time-stamped history of lux readings and uses the
# trend to predict whether the sun will persist over the next heating window.
#
# Prediction logic:
#   - Keep a rolling buffer of (timestamp, lux) pairs spanning LDR_TREND_WINDOW_S
#   - If the buffer has fewer than MIN_SAMPLES readings, return None (unknown)
#   - Compute the average lux over the window
#   - If the most recent lux reading is below LDR_TREND_DECLINE_RATIO of that
#     average, the trend is declining → forecast = False
#   - Otherwise, if the average lux is above LDR_SUNLIGHT_LUX, forecast = True
#   - Otherwise, forecast = False (not enough sun historically)
#
# The window is long enough (default 10 min) that a single passing cloud does
# not trigger a false "declining" flag.
# ─────────────────────────────────────────────────────────────────────────────

import time
from config import (
    LDR_TREND_WINDOW_S,
    LDR_TREND_DECLINE_RATIO,
    LDR_SUNLIGHT_LUX,
)

# Minimum number of samples before we make any prediction.
# At a 5s control loop interval, 6 samples = 30 seconds of history minimum.
_MIN_SAMPLES = 6

# Rolling buffer: list of [timestamp, lux] pairs
_history = []


def record(lux):
    """
    Call once per control loop cycle with the current lux reading.
    Appends to the rolling buffer and prunes entries older than the window.
    """
    now = time.time()
    _history.append((now, lux))

    # Prune old entries outside the trend window
    cutoff = now - LDR_TREND_WINDOW_S
    while _history and _history[0][0] < cutoff:
        _history.pop(0)


def forecast_ok():
    """
    Returns True if the LDR trend suggests sun will persist, False if declining
    or insufficient light, or None if not enough history yet to make a call.

    This is the no-WiFi fallback. It should only be called when:
      1) WiFi forecast is unavailable, OR
      2) The cached WiFi forecast is stale (older than LDR_FORECAST_STALE_S)
    """
    if len(_history) < _MIN_SAMPLES:
        return None   # Not enough data yet — caller should treat as unknown

    lux_values = [lux for _, lux in _history]
    avg_lux    = sum(lux_values) / len(lux_values)
    latest_lux = lux_values[-1]

    # Trend is declining if the most recent reading has dropped significantly
    # below the window average. The ratio threshold is tunable in config.py.
    if avg_lux > 0 and (latest_lux / avg_lux) < LDR_TREND_DECLINE_RATIO:
        print(f"  [LDR TREND] Declining — latest={latest_lux:.0f} lux, "
              f"avg={avg_lux:.0f} lux, ratio={latest_lux/avg_lux:.2f}")
        return False

    # Trend is stable — check if average light level is actually sunny
    if avg_lux >= LDR_SUNLIGHT_LUX:
        print(f"  [LDR TREND] Stable and sunny — avg={avg_lux:.0f} lux")
        return True

    print(f"  [LDR TREND] Stable but dim — avg={avg_lux:.0f} lux "
          f"(threshold={LDR_SUNLIGHT_LUX:.0f})")
    return False


def history_duration_s():
    """Returns how many seconds of history are currently buffered."""
    if len(_history) < 2:
        return 0
    return _history[-1][0] - _history[0][0]


def clear():
    """Clears the LDR history buffer. Useful for testing."""
    _history.clear()
