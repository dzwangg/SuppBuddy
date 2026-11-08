# SuppBuddy optical tester firmware

Firmware for the cuvette rig: four LEDs (white, red, green, blue), a **TCS34725** color sensor in line behind
the cuvette (transmitted light) and a **TSL2591** light sensor at 90° (scattered light). It speaks **Bluetooth
protocol v3** to the iPhone app (repo root README, "BLE contract"); the phone powers it over USB-C.
Readings are raw optical counts for screening, not a validated chemical or safety measurement.

## Upload

1. Keep the `SupplementOpticalTester/` folder intact (Arduino requires the folder name to match the `.ino`).
2. Open `SupplementOpticalTester.ino` in Arduino IDE. The `.h`/`.cpp` files appear as tabs.
3. Boards Manager: install **esp32 by Espressif Systems**. Library Manager: install **Adafruit TCS34725**,
   **Adafruit TSL2591 Library**, **Adafruit Unified Sensor**, **Adafruit BusIO** and **LiquidCrystal I2C**.
4. Select **ESP32 Dev Module** and the board's port, then upload. Or from a terminal:
   `arduino-cli compile --upload -p <port> --fqbn esp32:esp32:esp32 firmware/SupplementOpticalTester`
5. Unplug it from the computer and plug it into the iPhone. The app connects by itself.

## Bench test (Serial Monitor, 115200 baud, "Newline")

| Command | What it does |
|---|---|
| `status` | Which sensors and screen were detected, and whether a phone is connected |
| `led` | Lights each LED for half a second (wiring check) |
| `b` | Blank: settings line, a dark reading, then a water reading under each LED |
| `s` | A 30 s sample run, printing the same lines the phone receives |
| `i` | The settings line |
| `help` | Command list |

Every reading line ends with `r,g,b,c,full,ir`: the TCS34725 counts (averaged over 3 integrations), then
the TSL2591's full-spectrum and infrared counts. With clean water in a closed box, each LED's `B` line should
be well above the `D` line, no channel should be near its ceiling (21,504 for the TCS34725 at 50 ms; 37,888 for
the TSL2591 at 100 ms), and `ir` should stay close to the dark value.

## Wiring

The pin table is in the repo root README (one table for everyone); `Config.h` must match it. Each LED:
GPIO → its own 330 Ω resistor → LED long leg; short leg → GND.

**TCS34725 white LED:** wire the breakout's `LED` pin to **GPIO 4**. The firmware drives it LOW at power-up
(`RGBSensor::ledOff()`), so the LED stays off for every reading; it sits millimeters from the sensor and its
glare would bounce back into it. Tying `LED` to GND instead also works, and boards with `LED` wired to `INT`
are covered too. `status` in Serial Monitor reminds you which pin it uses.

## How a reading works

`Measurements::measure()` switches one LED on (or none, for dark), reads the TSL2591 (one 100 ms integration,
about 120 ms), then averages three TCS34725 integrations, which by then were all taken under the same light.
About 285 ms per reading; a cycle (dark + four LEDs) is about 1.4 s, so a 30 s run gives ~22 cycles.

Gains and integration times are fixed in `Config.h` and reported to the app in the `I` line. Change them only
together with the backend's reference settings (`REF_*` in its `.env`), or new scans won't compare with old ones.

## Files

| File | Responsibility |
|---|---|
| `SupplementOpticalTester.ino` | Setup, Bluetooth and Serial command handling |
| `Config.h` | Pins, sensor settings, timing |
| `LEDController.*` | The four LEDs, in cycle order (W, R, G, B) |
| `RGBSensor.*` | TCS34725 setup and averaged reads |
| `LuxSensor.*` | TSL2591 setup and full/infrared reads |
| `Measurements.*` | The protocol v3 sequences (blank, run) and line format |
| `BleLink.*` | Nordic UART Service over Bluetooth LE |

## Troubleshooting

- **App says a sensor isn't detected:** check that sensor's SDA/SCL pair, power, ground and solder joints
  (swapping SDA and SCL is the usual mistake), then press the board's EN/reset button.
- **A `B` line barely above `D`:** that LED is reversed, has no resistor path, or isn't aimed at the cuvette.
  A dim blue LED is OK: the backend falls back to white light for that color and notes it.
- **Scan fails with "light_leak":** room light is getting into the box; close it.
- **TSL2591 counts at the ceiling:** change `TSL_GAIN` to `TSL2591_GAIN_LOW` and `TSL_GAIN_X` to 1 in
  `Config.h`, and set `REF_TSL_GAIN=1` in the backend's `.env`.
