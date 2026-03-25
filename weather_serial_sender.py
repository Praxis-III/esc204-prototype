#!/usr/bin/env python3
"""
Laptop-side weather bridge.

Fetches weather from Open-Meteo and forwards it to a Pico over USB serial.
Protocol sent to Pico (one line per update):
    WEATHER {json_payload}\n
Requires:
    pip install requests pyserial
"""

import argparse
import glob
import json
import sys
import time

import requests

try:
    import serial  # type: ignore[reportMissingImports]
except ImportError:
    serial = None


def build_api_url(latitude, longitude):
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&hourly=cloudcover,precipitation,temperature_2m"
        "&daily=sunrise,sunset"
        "&forecast_days=2"
        "&timezone=auto"
    )


def fetch_weather(url, timeout_s=10):
    r = requests.get(url, timeout=timeout_s)
    r.raise_for_status()
    raw = r.json()

    hourly = raw.get("hourly", {})
    daily = raw.get("daily", {})

    hourly_time = hourly.get("time", [])[:24]
    hourly_cloud = hourly.get("cloudcover", [])[:24]
    hourly_precip = hourly.get("precipitation", [])[:24]
    hourly_temp = hourly.get("temperature_2m", [])[:24]

    return {
        "source": "open-meteo",
        "sent_at": int(time.time()),
        "hourly": {
            "time": hourly_time,
            "cloudcover": hourly_cloud,
            "precipitation": hourly_precip,
            "temperature_2m": hourly_temp,
        },
        "daily": {
            "time": daily.get("time", []),
            "sunrise": daily.get("sunrise", []),
            "sunset": daily.get("sunset", []),
        },
    }


def send_packet(ser, payload):
    line = "WEATHER " + json.dumps(payload, separators=(",", ":")) + "\n"
    ser.write(line.encode("utf-8"))
    ser.flush()
    return line


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch Open-Meteo weather and send to Pico over USB serial"
    )
    parser.add_argument("--port", default=None, help="Serial port, e.g. /dev/tty.usbmodem1101")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--interval", type=int, default=900, help="Send interval in seconds (default: 900)")
    parser.add_argument("--once", action="store_true", help="Send one update and exit")
    return parser.parse_args()


def get_default_coordinates():
    try:
        from config import LATITUDE, LONGITUDE

        return LATITUDE, LONGITUDE
    except Exception:
        return None, None


def detect_serial_port():
    """Finds a likely Pico serial port on macOS/Linux."""
    candidates = []

    if sys.platform.startswith("darwin") or sys.platform.startswith("linux"):
        candidates.extend(sorted(glob.glob("/dev/tty.usbmodem*")))
        candidates.extend(sorted(glob.glob("/dev/ttyACM*")))
        candidates.extend(sorted(glob.glob("/dev/ttyUSB*")))

    if len(candidates) == 1:
        return candidates[0]
    return None


def main():
    if serial is None:
        raise SystemExit("pyserial is not installed. Run: pip install pyserial")

    args = parse_args()

    default_lat, default_lon = get_default_coordinates()
    latitude = default_lat
    longitude = default_lon

    if latitude is None or longitude is None:
        raise SystemExit("Could not read LATITUDE/LONGITUDE from config.py")

    port = args.port or detect_serial_port()
    if port is None:
        raise SystemExit("Could not detect serial port. Pass --port /dev/tty.usbmodemXXXX")

    url = build_api_url(latitude, longitude)
    print(f"Using Open-Meteo URL for lat={latitude}, lon={longitude}")
    print(f"Opening serial port: {port} @ {args.baud}")

    with serial.Serial(port, args.baud, timeout=1) as ser:
        # Give the USB serial endpoint a moment to settle.
        time.sleep(2)

        while True:
            try:
                payload = fetch_weather(url)
                wire_line = send_packet(ser, payload)
                points = len(payload["hourly"]["time"])
                print(f"[{int(time.time())}] Sent weather packet ({points} hourly points)")
                print(f"[{int(time.time())}] Data sent: {wire_line.strip()}")
            except Exception as e:
                print(f"[{int(time.time())}] Weather send failed: {e}")

            if args.once:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
