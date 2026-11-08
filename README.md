# SuppBuddy

A pocket supplement tester: an ESP32 cuvette rig measures how a dissolved sample absorbs and scatters
light, the iPhone app collects the readings and the label, and the backend scores them against other
scans of the same product and against public records. **Code sets the verdict; Claude only explains it.**

| Folder | What |
|---|---|
| `SuppBuddy/` | SwiftUI iPhone app (iOS 17+) |
| `backend/suppbuddy-backend/` | FastAPI server: sensor features, crowd fingerprints, FDA/NIH lookups, verdict, Claude explanation ([README](backend/suppbuddy-backend/README.md)) |
| `firmware/SupplementOpticalTester/` | Tester firmware: real sensors, Bluetooth protocol v3 ([README](firmware/SupplementOpticalTester/README.md)) |
| `firmware-stub/` | Same protocol with fake readings, for testing the app on a bare ESP32 |
| `checks/` | App logic self-check, with real backend responses as fixtures |
| `.github/workflows/ci.yml` | Runs the backend tests, the app self-check and both firmware builds on every push and PR |

## Run it

1. **Backend** (holds the Claude API key; the app has no secrets):

   ```bash
   cd backend/suppbuddy-backend
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   cp .env.example .env              # put ANTHROPIC_API_KEY in .env
   .venv/bin/python -m scripts.seed_demo
   .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **App:** open `SuppBuddy.xcodeproj` and run. In the Simulator the default server (`http://127.0.0.1:8000`) works
   and a simulated tester replays the backend's simulator (genuine and cornstarch-cut vitamin C, alternating).
   On an iPhone, set your team under Signing & Capabilities, then in the app's Settings enter the laptop's
   address on the same Wi-Fi (`http://192.168.x.x:8000`) or an `ngrok http 8000` https address.

3. **Tester:** flash `firmware/SupplementOpticalTester` (Arduino IDE or `arduino-cli`, board `esp32:esp32:esp32`).
   Plug it into the iPhone's USB-C port for power; the app finds it over Bluetooth. Without sensors wired,
   flash `firmware-stub/suppbuddy_stub` instead.

After editing `project.yml`, regenerate with `xcodegen generate`.

Checks (CI runs the same ones):

```bash
swiftc SuppBuddy/Analysis.swift SuppBuddy/Server.swift SuppBuddy/NIH.swift checks/main.swift -o /tmp/suppbuddy-check && /tmp/suppbuddy-check
```

```bash
cd backend/suppbuddy-backend && .venv/bin/python -m pytest -q
```

## Flow

Blank (dark + clean water under each LED) → sample run (30 s of dark + white/red/green/blue
readings while it dissolves, charted live) → product (label photo read by Claude on the server, barcode
looked up in the NIH database, or typed; flavor too) → Analyze: the app posts `{label, readings, sample_prep}`
to `POST /scans`, polls `GET /scans/{id}`, shows the measured verdict within seconds and Claude's explanation
when it lands, then sends the result to the tester's screen. "Yes, this is …" calls `POST /scans/{id}/confirm`,
which adds the scan to that product's crowd reference, or holds it for review when it doesn't match an
established reference.

## Sample prep (protocol v3)

**500 mg of powder in 50 mL of water (10 g/L), stirred, poured into the cuvette.** Creatine only dissolves up
to about 17 g/L at 20 °C, so a stronger mix would leave genuine creatine cloudy. The app sends the amounts
(Settings → Sample prep); the server rescales color and cloudiness when a scan used a different amount.

## Hardware

Pins are defined in `firmware/SupplementOpticalTester/Config.h`; this table must match it.

| Part | ESP32 pin | Notes |
|---|---|---|
| TCS34725 SDA / SCL | 21 / 22 | In line behind the cuvette (transmitted light). I²C bus 0 |
| TCS34725 LED pin | GND | Keeps its white illumination LED off |
| TSL2591 SDA / SCL | 16 / 17 | 90° to the beam (scattered light). I²C bus 1, because both sensors use address 0x29 |
| Both sensors VIN / GND | 3V3 / GND | |
| White LED | 27 | Each LED: GPIO → its own 330 Ω resistor → LED (long leg) → GND |
| Red LED | 33 | |
| Green LED | 25 | |
| Blue LED | 26 | |
| 16×2 I²C LCD SDA / SCL | 21 / 22 | Shares bus 0 with the TCS34725 (LCD at 0x27 or 0x3F). VCC to 5V, GND to GND |

Use a WROOM-based ESP32 (GPIO 16/17 are taken by PSRAM on WROVER modules). Power comes from the iPhone's
USB-C port. If the board stays dark on a USB-C to USB-C cable, use Apple's USB-C to USB adapter with a USB-A
to USB-C cable (some boards lack the resistors that tell a USB-C source to turn power on).

## BLE contract, protocol v3

Data goes over Bluetooth LE, because iOS apps can't read an ESP32's USB serial without Apple's MFi program.
Nordic UART Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`, advertised as `SuppBuddy`. The app writes commands
to RX (`6E400002-…`); the tester answers with `\n`-terminated lines on TX (`6E400003-…`), `\r\n` is fine.
The same commands work typed into Arduino's Serial Monitor (115200 baud).

| App writes | Tester answers |
|---|---|
| `b` | `I,…`, then `D,<values>` (all LEDs off), then `B,<led>,<values>` for each LED with clean water in the cuvette, then `E` |
| `s` | `I,…`, then every ~1.4 s a cycle of `K,<t_ms>,<values>` (dark) and `S,<t_ms>,<led>,<values>` for each LED, for 30 s, then `E` |
| `L\|line1\|line2` | nothing; show the two lines on the tester's screen |

- `<values>` is `r,g,b,c,full,ir`: TCS34725 counts (averaged over 3 integrations, one decimal), then the
  TSL2591's full-spectrum and infrared counts.
- `<led>` is `W`, `R`, `G` or `B`, in that order.
- `I,v3,<tcs gain>,<tcs ms>,<tsl gain>,<tsl ms>,WRGB` reports the sensor settings. The backend derives
  saturation limits from them and warns when they differ from the reference settings.
- `X,<message>` then `E`: the tester can't measure (a sensor isn't detected); the app shows the message.
- The app gives up after 5 s without a line. Each line fits one notification (MTU 185; lines are under 70 bytes).
- The app still reads protocol v2 lines (white light only) from older stubs.

## Known shortcuts

- The crowd reference starts from simulated seed scans (`scripts/seed_demo.py`, marked synthetic). Replace
  them with about 5 real confirmed scans per demo product before judging.
- `backend/suppbuddy-backend/data/tainted_supplements.csv` ships empty; import FDA's list
  (`python -m scripts.import_tainted`) before the demo, or the tainted check is skipped.
- Scoring thresholds and record weights are first guesses; `grep -rn "TODO(" backend` lists them.
