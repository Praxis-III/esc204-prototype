# PVT Solar Control System

**Raspberry Pi Pico W · MicroPython **

---

## 1. What This System Does

This is the firmware for a solar thermal control system built around Photovoltaic-Thermal (PVT) panels. The system intelligently manages water flow between a supply tank, a PVT panel, and a storage tank. Its two primary goals are:

- Maximise the use of free solar energy to heat water
- Minimise grid electricity usage — the electric heater is a last resort, not a first response

It achieves this by reading temperatures, light levels, and tank volumes in real time, and combining that with a live weather forecast to make forward-looking decisions. For example, it will not start water flow if clouds are forecast to arrive before the water has had time to heat up in the PVT panel.

---

## 2. Physical System Layout

### 2.1 Tanks and Flow Path

- **Supply Tank:** Source of cold/fresh water. Has a motorised valve on its outlet pipe.
- **Storage Tank:** Where heated water accumulates. Has a motorised valve on its inlet, three temperature sensors, one pressure sensor, and an electric heater element.

Water flows in one direction only:

```
Supply Tank → [supply valve] → PVT Panel → [storage valve] → Storage Tank
```

Both valves must be open simultaneously for water to flow through the panel and into storage.

### 2.2 Sensors

| Sensor | Location | Type | Purpose |
|---|---|---|---|
| DS18B20 #1 (TOP) | Top of storage tank | Digital temperature | Detects hottest water layer |
| DS18B20 #2 (MID) | Centre of storage tank | Digital temperature | Tracks average storage temp |
| DS18B20 #3 (BOT) | Bottom of storage tank | Digital temperature | Detects coldest layer / thermal mixing |
| DS18B20 #4 (PVT) | Outlet of PVT panel | Digital temperature | Detects when panel output is hot enough |
| Pressure sensor | Storage tank | Analog (0–3.3V) | Measures water volume via pressure |
| LDR / Photoresistor | Facing sky | Analog (0–3.3V) | Detects whether sun is directly shining |

### 2.3 Actuators

| Actuator | Location | Connected To |
|---|---|---|
| Motorised valve (supply) | Supply tank outlet | GPIO14 via relay |
| Motorised valve (storage) | Storage tank inlet | GPIO15 via relay |
| Electric heater relay | Storage tank | GPIO16 via relay |

---

## 3. Design and Implementation Decisions

### 3.1 Why MicroPython, not C/C++

The Raspberry Pi Pico W supports both MicroPython and C/C++ via the Pico SDK. C/C++ offers better raw performance and lower memory usage. MicroPython was chosen because the control loop runs every 30 seconds so real-time performance is not a constraint, the code is far more readable and maintainable in Python for a small team, and the iteration cycle (edit, upload via Thonny, test) is significantly faster than compiling C. If the system were expanded to require sub-millisecond timing or very low power consumption, migrating to C would be warranted.

### 3.2 Why a Single Shared 1-Wire Bus for All Temperature Sensors

The DS18B20 sensors use the 1-Wire protocol, which allows multiple sensors to share a single data line. Rather than dedicating a separate GPIO pin to each of the four temperature sensors, all four are wired to GPIO4 and addressed by their unique factory-assigned serial numbers. This conserves GPIO pins for potential future expansion (flow meters, additional valves, a display). The trade-off is a slightly longer read cycle since all sensors are triggered together, but at 750ms per conversion this is well within the 30-second control loop budget.

### 3.3 Why the Control Loop Uses Priority-Based Case Evaluation

Rather than running all cases simultaneously and reconciling conflicting outputs, the controller evaluates cases in strict priority order and returns early once a high-priority case acts. This makes behaviour predictable: if freeze protection fires, nothing else runs that cycle. This pattern is deliberately chosen over a more complex state machine for clarity in this first iteration.

### 3.4 Why Hysteresis on the Heater

The heater turns on at 52°C and off at 60°C — not at the same threshold in both directions. Without this band, a storage temperature sitting at exactly 60°C would cause the heater to toggle on and off rapidly, which causes mechanical wear on relay contacts and heater elements. The hysteresis band ensures the heater stays on long enough to do meaningful work before switching off.

### 3.5 Why a 10-Minute Cloud Tolerance

When water is already flowing through the PVT circuit and a cloud briefly passes over, closing the supply valve immediately is counterproductive. Water already in the panel retains heat, the cloud may pass within minutes, and stopping and restarting flow has its own thermal cost. The 10-minute window is a reasonable compromise between responsiveness to genuinely deteriorating conditions and stability during transient cloud cover. It is not hardcoded — it lives in `controller.py` as `CLOUD_TOLERANCE_S` and can be tuned once real-world data is available.

### 3.6 Why Open-Meteo Was Chosen for Weather Data

Open-Meteo requires no API key, no account registration, and has no rate limiting for reasonable usage. This eliminates an entire category of failure modes — expired keys, billing issues, account problems — that would be inappropriate for an embedded system running unattended. The API returns hourly cloud cover and precipitation, which are the two variables most relevant to predicting solar irradiance. The forecast is cached locally for 15 minutes to avoid unnecessary network requests.

### 3.7 Why the Supply Tank Uses a Placeholder Fraction

The supply tank volume is not yet directly measured. The `_estimate_supply_fraction()` function in `controller.py` returns a fixed value of 1.0 as a deliberate temporary stub. Rather than blocking the rest of the system on a missing sensor, a clearly labelled placeholder was used with a `TODO` comment marking exactly where the real implementation goes when the hardware is available. The rest of the system runs and is fully testable in the meantime.

### 3.8 Why the Mixing Temperature Uses a Simple Energy Balance

When an emergency refill is triggered, the code estimates what temperature the storage tank will reach after cold PVT water mixes in. It uses a mass-weighted average — the standard energy balance for mixing two water volumes. A more sophisticated model could account for heat loss through tank walls and pipe thermal mass, but for the purpose of a binary decision (will temperature drop below 50°C: yes or no), the simple model is accurate enough and avoids the calibration overhead of a more detailed thermal model.

### 3.9 Why config.py Is Separated from All Other Files

All user-adjustable settings — Wi-Fi credentials, pin numbers, temperature thresholds, tank volumes, sensor addresses — live exclusively in `config.py`. No other file contains hardcoded values a user would need to change. This means updating the system for different hardware, a different location, or different operating parameters requires editing exactly one file. It also means the rest of the codebase can be version-controlled and shared without containing any site-specific or sensitive information.

### 3.10 Why boot.py Handles Wi-Fi Separately from main.py

MicroPython on the Pico W runs `boot.py` before `main.py` on every power-up. Wi-Fi connection is placed in `boot.py` so the network is established before any application code runs. This matters because `weather.py` attempts an API call early in the first control loop cycle. If Wi-Fi were initialised inside `main.py`, a race condition could cause the first weather fetch to fail silently. Keeping Wi-Fi setup in `boot.py` also makes it easy to add other early-startup tasks without touching the main application logic.

---

## 4. Code Files

| File | Purpose | Edit it? |
|---|---|---|
| `config.py` | All settings: Wi-Fi, pin numbers, thresholds, sensor addresses | Yes — always start here |
| `boot.py` | Runs first on power-up. Connects Pico W to Wi-Fi. | No |
| `main.py` | Entry point. Starts the control loop and keeps it running. | No |
| `controller.py` | The brain. Reads all sensors and decides what to do. | Only to add new logic |
| `sensors.py` | All sensor reading functions (temp, light, pressure). | No |
| `actuators.py` | Controls valves and heater. | No |
| `weather.py` | Fetches weather forecast from Open-Meteo API. | No |
| `test_scenarios.py` | Runs all logic tests without hardware. | Add new tests here |

---

## 5. Sensor Data — Expected Inputs and Ranges

### 5.1 DS18B20 Temperature Sensors

Protocol: 1-Wire digital. All four sensors share GPIO4 with a 4.7kΩ pull-up resistor to 3.3V.

| Property | Detail |
|---|---|
| Output | Temperature in °C (float), e.g. `58.5` |
| Useful range | 0°C to 90°C |
| Resolution | 0.0625°C (12-bit, default) |
| Conversion time | ~750ms per reading (handled automatically in `sensors.py`) |
| Wiring | VCC → 3.3V, GND → GND, DATA → GPIO4, one 4.7kΩ resistor DATA→3.3V |
| Addressing | Run `sensors.scan_sensors()` in Thonny REPL to retrieve addresses |

Key thresholds the controller uses:

- PVT sensor ≥ 60°C → water is hot enough to transfer to storage (Case 2)
- Storage average ≤ 52°C → turn heater on (Case 6)
- Storage average ≥ 60°C → turn heater off (Case 6)
- Storage top > 80°C → overtemperature emergency stop (Case 5)
- Any sensor ≤ 4°C → freeze protection activates (Case 4)

### 5.2 Photoresistor / LDR

Protocol: Analog voltage via ADC on GPIO26. Wired as a voltage divider: 3.3V → LDR → GPIO26 → 10kΩ → GND.

| Property | Detail |
|---|---|
| Output | Raw ADC integer, 0 to 65535 (16-bit) |
| Low value (dark) | LDR resistance high, voltage divider pulls GPIO26 low |
| High value (bright) | LDR resistance near zero, GPIO26 approaches 3.3V |
| Sun threshold | Raw ≥ 40000 = sun is out (`LDR_SUNLIGHT_THRESHOLD` in `config.py`) |
| Strong sun | Raw ≥ 55000 = direct bright sunlight |
| Tuning note | Thresholds must be calibrated outdoors — sensitivity varies by component |

### 5.3 Pressure Sensor (Storage Tank Volume)

Protocol: Analog voltage via ADC on GPIO27. Converts to volume using linear interpolation between two calibration points.

| Property | Detail |
|---|---|
| Output | Voltage proportional to water pressure |
| Water density assumed | 1 kg per litre |
| Calibration (empty) | Measure voltage with empty tank → `PRESSURE_VOLTAGE_AT_EMPTY` |
| Calibration (full) | Measure voltage with full tank → `PRESSURE_VOLTAGE_AT_FULL` |
| Code output | Volume in litres (float), clamped to 0–max |
| Max volume | `STORAGE_TANK_MAX_VOLUME_L` in `config.py` (default: 200L) |

---

## 6. Control Cases — Priority Order

The controller runs every 30 seconds. Cases are evaluated in priority order. When a higher-priority case fires, the loop returns early and lower cases are skipped for that cycle.

| Priority | Case | Trigger | Action |
|---|---|---|---|
| 1 | Freeze protection | Any sensor ≤ 4°C | Open storage valve (drain PVT), close supply, heater on |
| 2 | Overtemperature | Storage top > 80°C | Emergency stop — all outputs off |
| 3 | Supply tank low | Supply < 20% full | Open both valves; heater on if mixing drops below 50°C |
| 4 | Fill from PVT | PVT ≥ 60°C and storage not full | Open both valves |
| 5 | Start PVT flow | Sun out + good forecast + PVT cold | Open supply valve |
| 6 | Cloud transient | Sun gone briefly during active flow | Wait 10 min before stopping |
| 7 | Heater on | Storage average ≤ 52°C | Turn heater on |
| 8 | Heater off | Storage average ≥ 60°C | Turn heater off |
| 9 | Night mode | Dark and no active flow | Close storage valve (prevent heat loss) |
| 10 | Pre-emptive heat | No sun forecast 12h + storage < 60°C | Turn heater on now |

---

## 7. Weather Forecast Integration

The laptop-side bridge script fetches an hourly forecast from the Open-Meteo API and sends it to the Pico over USB serial. The two variables used are hourly cloud cover (0-100%) and precipitation (mm/hr). A forecast window equal to the expected PVT heat-up time is evaluated: if average cloud cover is below 50% and precipitation is below 0.5mm/hr across that window, the forecast is considered favourable.

If no weather packet has arrived yet, the forecast returns `None`. The controller treats an unknown forecast as permissive and will still start flow based on the photoresistor alone. The system degrades gracefully rather than refusing to operate.

---

## 8. Setup Order When Hardware Is Ready

1. Install MicroPython on the Pico W (hold BOOTSEL, plug in USB, drag `.uf2` file onto RPI-RP2 drive)
2. Install Thonny IDE from [thonny.org](https://thonny.org)
3. Edit `config.py`: set `LATITUDE` and `LONGITUDE`
4. Verify GPIO pin numbers in `config.py` match your physical wiring
5. Upload all `.py` files to the Pico W via Thonny (File → Save As → Raspberry Pi Pico)
6. On laptop: `pip install requests pyserial`
7. On laptop: run `python software/weather_serial_sender.py --port /dev/tty.usbmodemXXXX`
8. In Thonny REPL: `import sensors` then `sensors.scan_sensors()` — note all printed addresses
9. Identify which address belongs to which physical sensor (use warm/cold water to distinguish)
10. Paste the four addresses into `config.py`
11. Calibrate pressure sensor: record voltage at empty and full tank, update `config.py`
12. Re-upload `config.py`, press reset — system starts automatically

---

## 9. Testing Without Hardware

All control logic can be tested on any computer. `test_scenarios.py` mocks all hardware dependencies and runs 12 scenarios covering every control case:

```bash
python test_scenarios.py
```

Each test specifies exact sensor inputs, runs one control loop cycle, and checks the resulting actuator state. To add a new edge case test, define the sensor conditions, run the loop, and assert the expected outputs.

---

## 10. Hardware Setup Checklist

Complete before first real run. All changes go in `config.py` only.

| # | Item | Variable | Done |
|---|---|---|---|
| 1 | GPS latitude of installation | `LATITUDE` | ☐ |
| 2 | GPS longitude of installation | `LONGITUDE` | ☐ |
| 3 | GPIO pin numbers verified against wiring | All `*_PIN` values | ☐ |
| 4 | DS18B20 storage top address | `DS18B20_STORAGE_TOP` | ☐ |
| 5 | DS18B20 storage mid address | `DS18B20_STORAGE_MID` | ☐ |
| 6 | DS18B20 storage bottom address | `DS18B20_STORAGE_BOTTOM` | ☐ |
| 7 | DS18B20 PVT panel address | `DS18B20_PVT` | ☐ |
| 8 | Pressure sensor voltage at empty tank | `PRESSURE_VOLTAGE_AT_EMPTY` | ☐ |
| 9 | Pressure sensor voltage at full tank | `PRESSURE_VOLTAGE_AT_FULL` | ☐ |
| 10 | Actual storage tank max volume (litres) | `STORAGE_TANK_MAX_VOLUME_L` | ☐ |
| 11 | Actual supply tank max volume (litres) | `SUPPLY_TANK_MAX_VOLUME_L` | ☐ |


# esc204-prototype
The codebase for prototype in ESC204

## Control Logic Algorithm

The core decision-making process implemented in `controller.py` evaluates system states based on temperature sensors, ambient light, and supply thresholds to safely and efficiently manage the storage tanks and PVT loop.

```latex
\begin{algorithm}
\caption{System Controller Logic}
\begin{algorithmic}[1]
\LOOP
    \STATE Read sensors: $T_{storage}$, $T_{PVT}$, $V_{storage}$, LDR (Sunlight)
    \STATE Read external forecaster (Weather)

    \IF{$\min(T_{storage}, T_{PVT}) \le T_{freeze}$}
        \STATE \COMMENT{Case 4: Freeze Protection}
        \STATE Open storage valve; Close supply valve
        \STATE Turn heater ON
        \STATE \textbf{continue}
    \ENDIF

    \IF{$\max(T_{storage}) > T_{max\_safe}$}
        \STATE \COMMENT{Case 5: Overtemperature Emergency}
        \STATE Close all valves; Turn heater OFF
        \STATE \textbf{continue}
    \ENDIF

    \IF{$V_{supply} < V_{refill\_threshold}$}
        \STATE \COMMENT{Case 3: Emergency Supply Refill}
        \STATE Open supply valve; Open storage valve
        \IF{Predicted mixed temp $< T_{minimum}$}
            \STATE Turn heater ON
        \ENDIF
        \STATE \textbf{continue}
    \ENDIF

    \IF{$T_{PVT} \ge T_{PVT\_ready}$}
        \IF{$V_{storage}$ is FULL}
            \STATE \COMMENT{Case 8: Storage Full}
            \STATE Close all valves
        \ELSE
            \STATE \COMMENT{Case 2: Fill Storage}
            \STATE Open supply valve; Open storage valve
        \ENDIF
    \ELSIF{Supply Valve is CLOSED \AND Sun is OUT \AND Forecast is GOOD}
        \STATE \COMMENT{Case 1: Start PVT Flow}
        \STATE Open supply valve; Close storage valve
    \ELSIF{Sun is NOT OUT \AND Cloud Duration $> \text{Cloud Tolerance}$}
        \STATE \COMMENT{Case 9: Prolonged Cloud Cover}
        \STATE Close all valves
    \ENDIF

    \STATE \COMMENT{Heater Control (Cases 6 \& 10)}
    \IF{$T_{avg} \le T_{heater\_on} \OR$ (No Sun Expected \AND $T_{avg} < T_{target}$)}
        \STATE Turn heater ON
    \ELSIF{$T_{avg} \ge T_{heater\_off}$}
        \STATE Turn heater OFF
    \ENDIF

    \STATE \COMMENT{Case 7: Passive / Night Mode}
    \IF{Sun is NOT OUT \AND Supply valve is CLOSED}
        \STATE Close storage valve
    \ENDIF
\ENDLOOP
\end{algorithmic}
\end{algorithm}
```

# Pin Configuration

