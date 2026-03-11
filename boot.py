# boot.py
# This file runs FIRST when the Pico W powers on, before main.py.
# We use it only to connect to Wi-Fi so it's ready by the time main.py runs.

import network
import time
from config import WIFI_SSID, WIFI_PASSWORD

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("Already connected to Wi-Fi.")
        return True

    print(f"Connecting to Wi-Fi: {WIFI_SSID} ...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    # Wait up to 15 seconds for connection
    timeout = 15
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
        print(f"  Waiting... ({timeout}s left)")

    if wlan.isconnected():
        print(f"Connected! IP address: {wlan.ifconfig()[0]}")
        return True
    else:
        print("Wi-Fi connection FAILED. Will run without weather data.")
        return False

connect_wifi()
