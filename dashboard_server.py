#!/usr/bin/env python3
"""
Laptop-side dashboard server for the PVT Solar Control System.

Reads ``LOG_DATA {json}`` packets that the Pico W emits over USB serial after
every control-loop iteration.  Each packet is appended as a row to a CSV file
and the latest snapshot is held in memory.

A Flask web server is started at http://localhost:5000 and shows:
  • Current state of the solar-collector valve and electric heater
  • Current storage-tank fill level (%) and temperature (°C)
  • Control flags grouped by category (Safety, Tank Status, Solar, Control)
  • A scrollable table of all logged sensor data

Usage
-----
    python dashboard_server.py --port /dev/ttyACM0
    python dashboard_server.py --port COM3 --csv logs/sensor_log.csv
    python dashboard_server.py --demo            # fake data, no serial port needed

Requirements (laptop only)
--------------------------
    pip install flask pyserial
"""

import argparse
import csv
import glob
import json
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime

try:
    import serial  # type: ignore[reportMissingImports]
except ImportError:
    serial = None

try:
    from flask import Flask, jsonify, render_template_string  # type: ignore[reportMissingImports]
except ImportError:
    Flask = None  # type: ignore[assignment]

# ── Constants ─────────────────────────────────────────────────────────────────

LOG_PREFIX = "LOG_DATA "

CSV_HEADERS = [
    "datetime", "timestamp",
    "storage_temp_c", "pvt_temp_c", "lux",
    "storage_vol_l", "storage_pct",
    "valve_open", "heater_on",
    "sun_is_out", "pvt_ready", "forecast_ok",
    "freeze_flag", "overtemp_flag",
    "storage_full", "storage_low",
    "cloud_transient",
]

# ── Shared state (serial thread → Flask thread) ───────────────────────────────

_lock = threading.Lock()
_latest: dict = {}            # most-recent packet fields
_log_rows: deque = deque(maxlen=1000)  # last 1 000 rows kept in memory

# ── Helpers ───────────────────────────────────────────────────────────────────


def _detect_serial_port():
    """Auto-detect a likely Pico serial port on macOS / Linux."""
    candidates: list = []
    if sys.platform.startswith("darwin") or sys.platform.startswith("linux"):
        candidates += sorted(glob.glob("/dev/tty.usbmodem*"))
        candidates += sorted(glob.glob("/dev/ttyACM*"))
        candidates += sorted(glob.glob("/dev/ttyUSB*"))
    return candidates[0] if len(candidates) == 1 else None


def _packet_to_row(pkt: dict) -> dict:
    """Convert a LOG_DATA packet into a flat CSV-row dict."""
    ts = pkt.get("t", int(time.time()))
    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "datetime":       dt,
        "timestamp":      ts,
        "storage_temp_c": pkt.get("storage_temp"),
        "pvt_temp_c":     pkt.get("pvt_temp"),
        "lux":            pkt.get("lux"),
        "storage_vol_l":  pkt.get("storage_vol_l"),
        "storage_pct":    pkt.get("storage_pct"),
        "valve_open":     pkt.get("valve_open"),
        "heater_on":      pkt.get("heater_on"),
        "sun_is_out":     pkt.get("sun_is_out"),
        "pvt_ready":      pkt.get("pvt_ready"),
        "forecast_ok":    pkt.get("forecast_ok"),
        "freeze_flag":    pkt.get("freeze_flag"),
        "overtemp_flag":  pkt.get("overtemp_flag"),
        "storage_full":   pkt.get("storage_full"),
        "storage_low":    pkt.get("storage_low"),
        "cloud_transient": pkt.get("cloud_transient"),
    }


def _ingest(pkt: dict, csv_path: str, csv_writer, csv_file):
    """Store a parsed packet in memory and append it to the CSV file."""
    row = _packet_to_row(pkt)
    with _lock:
        _latest.update(pkt)
        _log_rows.append(row)
    csv_writer.writerow(row)
    csv_file.flush()


# ── Serial reader thread ──────────────────────────────────────────────────────


def serial_reader(port: str, baud: int, csv_path: str):
    """
    Opens the serial port and reads lines forever.
    Lines starting with LOG_DATA are parsed and stored.
    Other lines (Pico debug output) are forwarded to stdout so the operator
    can still see what the Pico is printing.
    """
    if serial is None:
        print("ERROR: pyserial is not installed.  Run: pip install pyserial", file=sys.stderr)
        return

    # Ensure the CSV output directory exists
    csv_dir = os.path.dirname(os.path.abspath(csv_path))
    os.makedirs(csv_dir, exist_ok=True)

    file_exists = os.path.isfile(csv_path)
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_HEADERS, extrasaction="ignore")
    try:
        if not file_exists:
            writer.writeheader()
            csv_file.flush()

        print(f"[serial] Opening {port} @ {baud} baud …")
        while True:
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    print(f"[serial] Connected. Waiting for LOG_DATA packets …")
                    while True:
                        raw = ser.readline()
                        if not raw:
                            continue
                        try:
                            line = raw.decode("utf-8", errors="replace").rstrip()
                        except Exception:
                            continue

                        if line.startswith(LOG_PREFIX):
                            try:
                                pkt = json.loads(line[len(LOG_PREFIX):])
                                _ingest(pkt, csv_path, writer, csv_file)
                            except Exception as exc:
                                print(f"[serial] Parse error: {exc}", file=sys.stderr)
                        else:
                            # Forward Pico debug output verbatim
                            print(f"[pico] {line}")

            except Exception as exc:
                print(f"[serial] Error: {exc} — retrying in 5 s …", file=sys.stderr)
                time.sleep(5)
    finally:
        csv_file.close()


# ── Demo data generator (--demo mode) ─────────────────────────────────────────


def demo_generator(csv_path: str):
    """Generate realistic fake packets every 5 seconds for demo/testing."""
    import math
    import random

    csv_dir = os.path.dirname(os.path.abspath(csv_path))
    os.makedirs(csv_dir, exist_ok=True)

    file_exists = os.path.isfile(csv_path)
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_HEADERS, extrasaction="ignore")
    try:
        if not file_exists:
            writer.writeheader()
            csv_file.flush()

        base_temp = 55.0
        t = 0
        print("[demo] Generating fake sensor data every 5 s …")
        while True:
            t += 1
            storage_temp = base_temp + 3 * math.sin(t / 10) + random.uniform(-0.5, 0.5)
            pvt_temp = 62.0 + 5 * math.sin(t / 8) + random.uniform(-1, 1)
            lux = max(0.0, 12000 + 8000 * math.sin(t / 15) + random.uniform(-500, 500))
            storage_pct = max(0.0, min(100.0, 70.0 + 10 * math.sin(t / 20)))
            sun_is_out = lux > 5000
            pvt_ready = pvt_temp >= 60.0
            valve_open = sun_is_out and pvt_ready and storage_pct < 99
            heater_on = storage_temp < 52.0

            pkt = {
                "t":             int(time.time()),
                "storage_temp":  round(storage_temp, 2),
                "pvt_temp":      round(pvt_temp, 2),
                "lux":           round(lux, 1),
                "storage_vol_l": round(storage_pct / 100 * 0.539, 3),
                "storage_pct":   round(storage_pct, 1),
                "valve_open":    valve_open,
                "heater_on":     heater_on,
                "sun_is_out":    sun_is_out,
                "pvt_ready":     pvt_ready,
                "forecast_ok":   True,
                "freeze_flag":   storage_temp < 4,
                "overtemp_flag": storage_temp > 80,
                "storage_full":  storage_pct >= 99,
                "storage_low":   storage_pct < 20,
                "cloud_transient": False,
            }
            _ingest(pkt, csv_path, writer, csv_file)
            time.sleep(5)
    finally:
        csv_file.close()


# ── Flask web application ─────────────────────────────────────────────────────

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PVT Solar Control — Dashboard</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"
      crossorigin="anonymous">
<style>
  body { background: #f0f2f5; font-family: 'Segoe UI', sans-serif; }
  .navbar { background: linear-gradient(135deg, #1a2a3a 0%, #2d4a6a 100%); }
  .status-card { border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
  .status-val  { font-size: 2.2rem; font-weight: 700; }
  .flag-row    { display: flex; align-items: center; gap: .5rem; margin: .25rem 0; }
  .dot         { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .dot-green   { background: #28a745; }
  .dot-red     { background: #dc3545; }
  .dot-grey    { background: #adb5bd; }
  .dot-warn    { background: #ffc107; }
  .table-scroll{ max-height: 380px; overflow-y: auto; }
  #last-update { font-size: .8rem; opacity: .75; }
</style>
</head>
<body>

<nav class="navbar navbar-dark px-4 py-3 mb-4">
  <span class="navbar-brand fs-5 fw-bold">☀️  PVT Solar Control — Live Dashboard</span>
  <span class="text-white-50" id="last-update">Waiting for data…</span>
</nav>

<div class="container-fluid px-4">

  <!-- ── Status cards ─────────────────────────────────────────────────────── -->
  <div class="row g-3 mb-4">

    <div class="col-6 col-md-3">
      <div class="card status-card text-center p-3 h-100">
        <div class="text-muted small mb-1">Solar Collector Valve</div>
        <div class="status-val" id="card-valve">—</div>
        <div class="small mt-1" id="card-valve-sub"></div>
      </div>
    </div>

    <div class="col-6 col-md-3">
      <div class="card status-card text-center p-3 h-100">
        <div class="text-muted small mb-1">Electric Heater</div>
        <div class="status-val" id="card-heater">—</div>
        <div class="small mt-1" id="card-heater-sub"></div>
      </div>
    </div>

    <div class="col-6 col-md-3">
      <div class="card status-card text-center p-3 h-100">
        <div class="text-muted small mb-1">Tank Content</div>
        <div class="status-val" id="card-tank-pct">—</div>
        <div class="progress mt-2" style="height:10px">
          <div id="tank-bar" class="progress-bar" style="width:0%"></div>
        </div>
      </div>
    </div>

    <div class="col-6 col-md-3">
      <div class="card status-card text-center p-3 h-100">
        <div class="text-muted small mb-1">Tank Temperature</div>
        <div class="status-val" id="card-tank-temp">—</div>
        <div class="small mt-1 text-muted">PVT: <span id="pvt-temp">—</span></div>
      </div>
    </div>

  </div><!-- /status cards -->

  <!-- ── Control flags ────────────────────────────────────────────────────── -->
  <div class="row g-3 mb-4">

    <div class="col-12 col-md-6 col-lg-3">
      <div class="card status-card p-3 h-100">
        <div class="fw-semibold mb-2">🛡 Safety</div>
        <div class="flag-row">
          <span class="dot" id="dot-freeze"></span>
          <span id="lbl-freeze">Freeze protection</span>
        </div>
        <div class="flag-row">
          <span class="dot" id="dot-overtemp"></span>
          <span id="lbl-overtemp">Overtemperature</span>
        </div>
      </div>
    </div>

    <div class="col-12 col-md-6 col-lg-3">
      <div class="card status-card p-3 h-100">
        <div class="fw-semibold mb-2">🪣 Tank Status</div>
        <div class="flag-row">
          <span class="dot" id="dot-storage-full"></span>
          <span id="lbl-storage-full">Storage full</span>
        </div>
        <div class="flag-row">
          <span class="dot" id="dot-storage-low"></span>
          <span id="lbl-storage-low">Storage low — needs refill</span>
        </div>
      </div>
    </div>

    <div class="col-12 col-md-6 col-lg-3">
      <div class="card status-card p-3 h-100">
        <div class="fw-semibold mb-2">☀️ Solar Conditions</div>
        <div class="flag-row">
          <span class="dot" id="dot-sun"></span>
          <span>Sun is out (<span id="lbl-lux">—</span> lux)</span>
        </div>
        <div class="flag-row">
          <span class="dot" id="dot-pvt-ready"></span>
          <span>PVT ready (≥ 60 °C)</span>
        </div>
        <div class="flag-row">
          <span class="dot" id="dot-forecast"></span>
          <span id="lbl-forecast">Forecast</span>
        </div>
      </div>
    </div>

    <div class="col-12 col-md-6 col-lg-3">
      <div class="card status-card p-3 h-100">
        <div class="fw-semibold mb-2">⚙️ Control State</div>
        <div class="flag-row">
          <span class="dot" id="dot-cloud"></span>
          <span>Cloud transient (10 min grace)</span>
        </div>
        <div class="flag-row">
          <span class="dot dot-grey" id="dot-valve-open"></span>
          <span>Valve open</span>
        </div>
        <div class="flag-row">
          <span class="dot dot-grey" id="dot-heater-on"></span>
          <span>Heater on</span>
        </div>
      </div>
    </div>

  </div><!-- /flags -->

  <!-- ── Sensor log table ─────────────────────────────────────────────────── -->
  <div class="card status-card mb-5">
    <div class="card-header d-flex justify-content-between align-items-center">
      <span class="fw-semibold">📋 Sensor &amp; Motor Log</span>
      <span class="text-muted small"><span id="row-count">0</span> rows logged</span>
    </div>
    <div class="card-body p-0">
      <div class="table-scroll">
        <table class="table table-sm table-striped table-hover mb-0" id="log-table">
          <thead class="table-dark sticky-top">
            <tr>
              <th>Time</th>
              <th>Storage °C</th>
              <th>PVT °C</th>
              <th>Lux</th>
              <th>Tank %</th>
              <th>Vol (L)</th>
              <th>Valve</th>
              <th>Heater</th>
              <th>Sun</th>
              <th>PVT Rdy</th>
              <th>Forecast</th>
              <th>❄ Freeze</th>
              <th>🌡 OTemp</th>
              <th>Full</th>
              <th>Low</th>
              <th>☁ Trans.</th>
            </tr>
          </thead>
          <tbody id="log-body">
            <tr><td colspan="16" class="text-center text-muted py-4">
              Waiting for first LOG_DATA packet…
            </td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div><!-- /container -->

<script>
// ── helpers ──────────────────────────────────────────────────────────────────

function setDot(id, active, warnOnActive) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'dot ' + (active === null ? 'dot-grey'
                         : active          ? (warnOnActive ? 'dot-warn' : 'dot-green')
                                           : 'dot-grey');
}

function boolBadge(v) {
  if (v === null || v === undefined) return '<span class="badge bg-secondary">?</span>';
  return v ? '<span class="badge bg-success">YES</span>'
           : '<span class="badge bg-secondary">NO</span>';
}

function fmtVal(v, suffix) {
  if (v === null || v === undefined) return '—';
  return v + (suffix || '');
}

// ── status update ─────────────────────────────────────────────────────────────

function applyStatus(d) {
  // Valve
  const valveEl = document.getElementById('card-valve');
  if (d.valve_open === true) {
    valveEl.textContent = 'OPEN';
    valveEl.style.color = '#28a745';
  } else if (d.valve_open === false) {
    valveEl.textContent = 'CLOSED';
    valveEl.style.color = '#6c757d';
  } else {
    valveEl.textContent = '—';
    valveEl.style.color = '';
  }

  // Heater
  const heatEl = document.getElementById('card-heater');
  if (d.heater_on === true) {
    heatEl.textContent = 'ON';
    heatEl.style.color = '#dc3545';
  } else if (d.heater_on === false) {
    heatEl.textContent = 'OFF';
    heatEl.style.color = '#6c757d';
  } else {
    heatEl.textContent = '—';
    heatEl.style.color = '';
  }

  // Tank %
  const pct = d.storage_pct;
  document.getElementById('card-tank-pct').textContent =
    pct !== undefined && pct !== null ? pct.toFixed(1) + ' %' : '—';
  const bar = document.getElementById('tank-bar');
  bar.style.width = (pct || 0) + '%';
  bar.className = 'progress-bar ' +
    (pct >= 99 ? 'bg-info' : pct < 20 ? 'bg-danger' : 'bg-success');

  // Temperature
  const st = d.storage_temp;
  document.getElementById('card-tank-temp').textContent =
    st !== undefined && st !== null ? st.toFixed(1) + ' °C' : '—';
  const pt = d.pvt_temp;
  document.getElementById('pvt-temp').textContent =
    pt !== undefined && pt !== null ? pt.toFixed(1) + ' °C' : '—';

  // ── Flags ──────────────────────────────────────────────────────────────────

  // Safety
  setDot('dot-freeze',   d.freeze_flag,   true);
  setDot('dot-overtemp', d.overtemp_flag, true);

  // Tank status
  setDot('dot-storage-full', d.storage_full, false);
  setDot('dot-storage-low',  d.storage_low,  true);

  // Solar
  setDot('dot-sun',        d.sun_is_out,  false);
  setDot('dot-pvt-ready',  d.pvt_ready,   false);
  const fc = d.forecast_ok;
  const fcDot = document.getElementById('dot-forecast');
  const fcLbl = document.getElementById('lbl-forecast');
  if (fc === null || fc === undefined) {
    fcDot.className = 'dot dot-grey';
    fcLbl.textContent = 'Forecast unknown';
  } else if (fc) {
    fcDot.className = 'dot dot-green';
    fcLbl.textContent = 'Forecast: sun expected';
  } else {
    fcDot.className = 'dot dot-grey';
    fcLbl.textContent = 'Forecast: no sun soon';
  }

  // Lux label
  const lux = d.lux;
  document.getElementById('lbl-lux').textContent =
    lux !== undefined && lux !== null ? lux.toFixed(0) : '—';

  // Control state
  setDot('dot-cloud',      d.cloud_transient, true);
  setDot('dot-valve-open', d.valve_open,      false);
  setDot('dot-heater-on',  d.heater_on,       true);

  // Timestamp
  if (d.t) {
    const dt = new Date(d.t * 1000);
    document.getElementById('last-update').textContent =
      'Last update: ' + dt.toLocaleTimeString();
  }
}

// ── log table update ──────────────────────────────────────────────────────────

function applyLogs(rows) {
  document.getElementById('row-count').textContent = rows.length;
  if (!rows.length) return;

  const tbody = document.getElementById('log-body');
  // Build rows newest-first
  const html = rows.slice().reverse().map(r => {
    const v = r.valve_open;
    const h = r.heater_on;
    return `<tr>
      <td class="text-nowrap">${r.datetime || '—'}</td>
      <td>${r.storage_temp_c !== null && r.storage_temp_c !== undefined ? (+r.storage_temp_c).toFixed(1) : '—'}</td>
      <td>${r.pvt_temp_c     !== null && r.pvt_temp_c     !== undefined ? (+r.pvt_temp_c    ).toFixed(1) : '—'}</td>
      <td>${r.lux            !== null && r.lux            !== undefined ? (+r.lux           ).toFixed(0) : '—'}</td>
      <td>${r.storage_pct    !== null && r.storage_pct    !== undefined ? (+r.storage_pct   ).toFixed(1) : '—'}</td>
      <td>${r.storage_vol_l  !== null && r.storage_vol_l  !== undefined ? (+r.storage_vol_l ).toFixed(3) : '—'}</td>
      <td>${v === true  ? '<span class="badge bg-success">OPEN</span>'
         : v === false ? '<span class="badge bg-secondary">CLOSED</span>' : '—'}</td>
      <td>${h === true  ? '<span class="badge bg-danger">ON</span>'
         : h === false ? '<span class="badge bg-secondary">OFF</span>' : '—'}</td>
      <td>${boolBadge(r.sun_is_out)}</td>
      <td>${boolBadge(r.pvt_ready)}</td>
      <td>${r.forecast_ok === null ? '<span class="badge bg-warning text-dark">?</span>'
         : boolBadge(r.forecast_ok)}</td>
      <td>${r.freeze_flag   ? '<span class="badge bg-warning text-dark">YES</span>' : '—'}</td>
      <td>${r.overtemp_flag ? '<span class="badge bg-danger">YES</span>'            : '—'}</td>
      <td>${r.storage_full  ? '<span class="badge bg-info text-dark">FULL</span>'   : '—'}</td>
      <td>${r.storage_low   ? '<span class="badge bg-warning text-dark">LOW</span>' : '—'}</td>
      <td>${r.cloud_transient ? '<span class="badge bg-warning text-dark">YES</span>' : '—'}</td>
    </tr>`;
  }).join('');
  tbody.innerHTML = html;
}

// ── polling ───────────────────────────────────────────────────────────────────

function pollStatus() {
  fetch('/api/status')
    .then(r => r.json())
    .then(d => applyStatus(d))
    .catch(() => {});
}

function pollLogs() {
  fetch('/api/logs')
    .then(r => r.json())
    .then(d => applyLogs(d))
    .catch(() => {});
}

pollStatus();
pollLogs();
setInterval(pollStatus, 5000);
setInterval(pollLogs,   10000);
</script>
</body>
</html>
"""  # end of HTML template


def build_app() -> "Flask":
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(_HTML_TEMPLATE)

    @app.route("/api/status")
    def api_status():
        with _lock:
            return jsonify(dict(_latest))

    @app.route("/api/logs")
    def api_logs():
        with _lock:
            return jsonify(list(_log_rows))

    return app


# ── CLI entry point ───────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(
        description="PVT Solar Control — laptop-side dashboard server"
    )
    p.add_argument(
        "--port",
        default=None,
        help="Serial port connected to the Pico W, e.g. /dev/ttyACM0 or COM3",
    )
    p.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200)",
    )
    p.add_argument(
        "--csv",
        default="sensor_log.csv",
        help="Path to the CSV log file (default: sensor_log.csv)",
    )
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web-server bind address (default: 127.0.0.1). "
             "Use 0.0.0.0 to expose the dashboard on all network interfaces.",
    )
    p.add_argument(
        "--web-port",
        type=int,
        default=5000,
        help="Web-server port (default: 5000)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="Generate synthetic data instead of reading from serial (no Pico required)",
    )
    return p.parse_args()


def main():
    if Flask is None:
        raise SystemExit(
            "Flask is not installed.  Run:  pip install flask pyserial"
        )

    args = parse_args()

    if args.demo:
        # Start demo data generator in background
        t = threading.Thread(
            target=demo_generator, args=(args.csv,), daemon=True
        )
        t.start()
        print(f"[demo] Fake data is being written to {args.csv}")
    else:
        # Require a serial port
        port = args.port or _detect_serial_port()
        if port is None:
            raise SystemExit(
                "Could not auto-detect a serial port.  "
                "Pass --port /dev/ttyACM0 (or COM3 on Windows)."
            )
        t = threading.Thread(
            target=serial_reader, args=(port, args.baud, args.csv), daemon=True
        )
        t.start()

    app = build_app()
    print(f"[web]    Dashboard available at  http://localhost:{args.web_port}")
    print(f"[web]    CSV log path:            {os.path.abspath(args.csv)}")
    app.run(host=args.host, port=args.web_port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
