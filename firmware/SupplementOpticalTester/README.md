# ESP32 Supplement Optical Tester

A modular Arduino IDE project for the **five discrete LEDs**, **TCS34725 color sensor**, and **TSL2591 lux sensor** used in the optical supplement-screening prototype.

> **Status:** standalone bench/calibration firmware. It talks over **USB Serial only** — it does not yet implement the BLE protocol the SupPal app expects (see the repo root `README.md`; `firmware-stub/suppal_stub` provides that with fake readings). Readings are raw optical counts for prototyping, not a validated chemical or safety measurement.

The code is organized so that the LED, RGB sensor, and lux sensor logic each lives in exactly one pair of source files. There is **one `setup()` and one `loop()`**, in `SupplementOpticalTester.ino`, so Arduino IDE compiles all tabs together without duplicate-function errors.

## Open and upload

1. Keep the `SupplementOpticalTester/` folder intact (Arduino requires the folder name to match the `.ino`).
2. Open `firmware/SupplementOpticalTester/SupplementOpticalTester.ino` in Arduino IDE. Its `.h` and `.cpp` siblings will appear as tabs.
3. In Library Manager, install **Adafruit TCS34725**, **Adafruit TSL2591 Library**, **Adafruit Unified Sensor**, and **Adafruit BusIO** (dependencies may auto-install). `Wire` is built in.
4. Select **ESP32 Dev Module** (for a classic ESP32-WROOM-32 board), select its COM port, and upload.
5. Open **Serial Monitor at 115200 baud**. Choose **Newline** in the line-ending selector; type a command and press Enter.

The LEDs chase automatically after boot, so you can see the LED controller working without typing anything.

## Serial Monitor commands

| Command | What it does | Uses |
|---|---|---|
| `led` | Five LEDs flash in sequence | LEDController only |
| `on` | All five LEDs stay on | LEDController only |
| `off` | All five LEDs off | LEDController only |
| `rgb` | Cycle each LED; show TCS34725 ambient, illuminated, corrected RGBC counts and approximate color | LED + RGBSensor |
| `lux` | Cycle each LED; show TSL2591 full, IR, visible counts, lux and LED-off/LED-on difference | LED + LuxSensor |
| `scan` | Cycle each LED; output **CSV rows** with BOTH sensors (and one CSV header on mode entry) | All modules |
| `ambient` | LEDs off; periodically show each available sensor's background measurements | Both sensors |
| `status` | Report detected sensor availability | Both sensors |
| `help` | Print command menu | Main sketch |

If only one sensor is detected, `rgb` or `lux` still works independently. `scan` logs whichever sensor is available, leaving missing fields blank. Reconnect wiring and reset the ESP32 to retry initialization.

## Wiring — 38-pin classic ESP32 DevKit (ESP32-WROOM)

Each standard, low-current, two-legged LED: **ESP32 GPIO → its own 330 Ω resistor → LED anode (+)**; **LED cathode (−) → common ESP32 GND**.

| Component | ESP32 pin |
|---|---|
| Red LED | GPIO 25 |
| Green LED | GPIO 26 |
| Yellow LED | GPIO 32 |
| Blue LED | GPIO 27 |
| White LED | GPIO 33 |
| TCS34725 SDA | GPIO 21 |
| TCS34725 SCL | GPIO 22 |
| TSL2591 SDA | GPIO 16 |
| TSL2591 SCL | GPIO 17 |
| Both sensor VIN | 3V3, assuming breakout accepts 3.3 V at VIN |
| Both sensor GND | GND |

**Why two I²C buses?** TCS34725 and TSL2591 both have address `0x29`. The classic ESP32 supports bus 0 (`Wire`) and bus 1 (`TwoWire(1)`), allowing simultaneous use. GPIO 16/17 may be unavailable on some ESP32 variants (e.g. certain WROVER modules): inspect your actual board.

Sensor breakouts need soldered header connections and I²C pull-ups. Adafruit-style modules generally include pull-ups. Do not connect either sensor to 5 V GPIO logic. Do not connect a high-power LED module directly to an ESP32 GPIO.

## Source layout

| File | Responsibility |
|---|---|
| `SupplementOpticalTester.ino` | Program entry point and serial command mode selection |
| `Config.h` | Configurable SDA/SCL pins, timing, baud rate |
| `LEDController.h/.cpp` | Pin mapping, one-at-a-time/on/off control of five LEDs |
| `RGBSensor.h/.cpp` | TCS34725 library setup, RGBC reads, ambient subtraction, approximate color label |
| `LuxSensor.h/.cpp` | TSL2591 setup, full/IR/visible/lux data, validity handling |
| `Measurements.h/.cpp` | Shared dark/on measurement cycle, per-sensor output, combined CSV |

## CSV fields (`scan` mode)

`timestamp_ms,led,rgb_guess,rgb_dark_r,rgb_dark_g,rgb_dark_b,rgb_dark_clear,rgb_on_r,rgb_on_g,rgb_on_b,rgb_on_clear,rgb_delta_r,rgb_delta_g,rgb_delta_b,rgb_delta_clear,tsl_dark_full,tsl_dark_ir,tsl_on_full,tsl_on_ir,tsl_on_visible,tsl_on_lux,tsl_dark_lux,tsl_lux_change`

Dark means the five controlled LEDs were off. `rgb_delta_*` is **LED-on minus LED-off**, which can be negative when there is noise/drift. A `tsl_lux_change` of zero or negative is not an error by itself; geometry or noise can explain it. The lux figure depends on the sensor's wavelength sensitivity and is not a chemical measurement. `rgb_guess` is approximate and may mislabel white/yellow/light-blue until calibrated.

**Measurement caveat:** The two sensors are read sequentially, not at the exact same instant. Keep the LED steady while both reads complete. For useful comparisons, maintain identical sample distance, geometry, stirring, temperature, sample mass, water volume and integration/gain settings. For quantitative tests use a water blank and LED-off backgrounds; do not assume optical similarity proves chemical identity, purity, safety or protein content.

## Common troubleshooting

- **`Adafruit_TCS34725.h` missing:** install **Adafruit TCS34725** from Arduino Library Manager.
- **`Adafruit_TSL2591.h` missing:** install **Adafruit TSL2591 Library**.
- **`Adafruit_Sensor.h` missing:** install **Adafruit Unified Sensor**.
- **`Adafruit_I2CDevice.h` missing:** install **Adafruit BusIO**.
- **TSL not detected:** verify separate SDA GPIO16/SCL GPIO17 bus, power, ground, and solder joints; temporarily test alone on known-working GPIO21/22 with TCS disconnected.
- **No serial output:** verify the COM port, 115200 baud, and press EN/RESET.
- **White TCS board illumination:** if your breakout has an onboard white LED, cover or disable it as directed for your exact breakout (some versions require a physical LED-to-INT connection to control it through software).
- **TSL saturating:** change `TSL2591_GAIN_MED` to `TSL2591_GAIN_LOW` in `LuxSensor.cpp` and re-upload.

## API references

- https://github.com/adafruit/Adafruit_TCS34725
- https://github.com/adafruit/Adafruit_TSL2591_Library
