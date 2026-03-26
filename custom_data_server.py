#!/usr/bin/env python3
"""
Laptop-side custom data server with a simple GUI.

Sends artificial testing packets to the Pico over USB serial:
    CUSTOM_DATA {json_payload}\n

Requires:
    pip install pyserial
"""

import argparse
import glob
import json
import sys
import time
import tkinter as tk
from tkinter import ttk

try:
    import serial
except ImportError:
    serial = None


def detect_serial_port():
    candidates = []

    if sys.platform.startswith("darwin") or sys.platform.startswith("linux"):
        candidates.extend(sorted(glob.glob("/dev/tty.usbmodem*")))
        candidates.extend(sorted(glob.glob("/dev/ttyACM*")))
        candidates.extend(sorted(glob.glob("/dev/ttyUSB*")))

    if len(candidates) == 1:
        return candidates[0]
    return None


def parse_args():
    parser = argparse.ArgumentParser(description="Send custom sensor test data to Pico over serial")
    parser.add_argument("--port", default=None, help="Serial port, e.g. /dev/tty.usbmodem1101")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--interval", type=int, default=5, help="Auto-send interval in seconds (default: 5)")
    return parser.parse_args()


class CustomDataGUI:
    def __init__(self, root, ser, interval_s):
        self.root = root
        self.ser = ser
        self.interval_s = max(1, int(interval_s))
        self.auto_send_enabled = tk.BooleanVar(value=False)

        self.tank_capacity_pct = tk.DoubleVar(value=75.0)
        self.solar_lux = tk.DoubleVar(value=20000.0)
        self.pvt_temp_c = tk.DoubleVar(value=62.0)
        self.tank_temp_c = tk.DoubleVar(value=52.0)
        self.next_hour_solar_available = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="Ready. Press Send once or enable Auto-send.")

        self._build_layout()

    def _build_layout(self):
        self.root.title("Custom Data Server")
        self.root.geometry("560x400")
        self.root.minsize(500, 360)

        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        row = 0
        self._add_labeled_scale(
            frame,
            row,
            "Tank capacity (%)",
            self.tank_capacity_pct,
            0,
            100,
            1,
        )
        row += 1

        self._add_labeled_scale(
            frame,
            row,
            "Current solar intensity (lux)",
            self.solar_lux,
            0,
            120000,
            100,
        )
        row += 1

        self._add_labeled_scale(
            frame,
            row,
            "PVT temperature (C)",
            self.pvt_temp_c,
            -10,
            100,
            1,
        )
        row += 1

        self._add_labeled_scale(
            frame,
            row,
            "Tank temperature (C)",
            self.tank_temp_c,
            -10,
            100,
            1,
        )
        row += 1

        ttk.Checkbutton(
            frame,
            text="Next hour solar available forecast",
            variable=self.next_hour_solar_available,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 10))
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        ttk.Button(buttons, text="Send now", command=self.send_now).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Checkbutton(buttons, text="Auto-send", variable=self.auto_send_enabled, command=self._toggle_auto_send).grid(
            row=0, column=1, sticky="w"
        )
        row += 1

        ttk.Label(frame, textvariable=self.status_text, wraplength=520).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        frame.columnconfigure(1, weight=1)

    def _add_labeled_scale(self, parent, row, label, variable, min_v, max_v, step):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)

        ttk.Scale(parent, from_=min_v, to=max_v, variable=variable).grid(
            row=row, column=1, sticky="ew", padx=8, pady=4
        )

        spin = tk.Spinbox(
            parent,
            from_=min_v,
            to=max_v,
            increment=step,
            textvariable=variable,
            width=10,
        )
        spin.grid(row=row, column=2, sticky="e", pady=4)

    def _build_payload(self):
        return {
            "tank_capacity_pct": float(self.tank_capacity_pct.get()),
            "solar_lux": float(self.solar_lux.get()),
            "pvt_temp_c": float(self.pvt_temp_c.get()),
            "tank_temp_c": float(self.tank_temp_c.get()),
            "next_hour_solar_available": bool(self.next_hour_solar_available.get()),
            "sent_at": int(time.time()),
            "source": "custom-data-server",
        }

    def send_now(self):
        payload = self._build_payload()
        line = "CUSTOM_DATA " + json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            self.ser.write(line.encode("utf-8"))
            self.ser.flush()
            self.status_text.set(f"Sent: {line.strip()}")
        except Exception as e:
            self.status_text.set(f"Send failed: {e}")

    def _toggle_auto_send(self):
        if self.auto_send_enabled.get():
            self.status_text.set(f"Auto-send enabled ({self.interval_s}s interval)")
            self._auto_send_loop()
        else:
            self.status_text.set("Auto-send disabled")

    def _auto_send_loop(self):
        if not self.auto_send_enabled.get():
            return
        self.send_now()
        self.root.after(self.interval_s * 1000, self._auto_send_loop)


def main():
    if serial is None:
        raise SystemExit("pyserial is not installed. Run: pip install pyserial")

    args = parse_args()
    port = args.port or detect_serial_port()

    if port is None:
        raise SystemExit("Could not detect serial port. Pass --port /dev/tty.usbmodemXXXX")

    print(f"Opening serial port: {port} @ {args.baud}")
    ser = serial.Serial(port, args.baud, timeout=1)
    time.sleep(2)

    root = tk.Tk()
    gui = CustomDataGUI(root, ser, args.interval)

    def _shutdown():
        try:
            ser.close()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _shutdown)
    root.mainloop()


if __name__ == "__main__":
    main()
