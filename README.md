# SupPal

A pocket supplement tester: an ESP32 cuvette rig measures how a dissolved sample absorbs and scatters
light, the iPhone app collects the readings and the label, and the backend scores them against other
scans of the same product and against public records. **Code sets the verdict; Claude only explains it.**

| Folder | What |
|---|---|
| `SupPal/` | SwiftUI iPhone app (iOS 17+) |
| `backend/suppbuddy-backend/` | FastAPI server: sensor features, crowd fingerprints, FDA/NIH lookups, verdict, Claude explanation ([README](backend/suppbuddy-backend/README.md)) |
| `firmware-stub/` | ESP32 test sketch that speaks the BLE protocol with fake readings |
| `checks/` | App logic self-check, with real backend responses as fixtures |

## Run it

1. **Backend** (holds the Claude API key; the app has no secrets):

   ```bash
   cd backend/suppbuddy-backend
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   cp .env.example .env              # put ANTHROPIC_API_KEY in .env
   .venv/bin/python -m scripts.seed_demo
   .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **App:** open `SupPal.xcodeproj` and run. In the Simulator the default server (`http://127.0.0.1:8000`) works
   and a simulated tester replays the backend's simulator (genuine and cornstarch-cut vitamin C, alternating).
   On an iPhone, set your team under Signing & Capabilities, then in the app's Settings enter the laptop's
   address on the same Wi-Fi (`http://192.168.x.x:8000`) or an `ngrok http 8000` https address.

3. **Tester:** flash `firmware-stub/suppal_stub` (Arduino IDE or `arduino-cli`, board `esp32:esp32:esp32`)
   until the real firmware exists.

After editing `project.yml`, regenerate with `xcodegen generate`.

Checks:

```bash
swiftc SupPal/Analysis.swift SupPal/Server.swift SupPal/NIH.swift checks/main.swift -o /tmp/suppal-check && /tmp/suppal-check
```

```bash
cd backend/suppbuddy-backend && .venv/bin/python -m pytest -q
```

## Flow

Blank (dark + clean water) → sample run (about 60 one-second readings while it dissolves, charted live) →
product (label photo read by Claude on the server, barcode looked up in the NIH database, or typed) →
Analyze: the app posts `{label, readings}` to `POST /scans`, polls `GET /scans/{id}`, shows the measured
verdict within seconds and Claude's explanation when it lands, then sends the result to the tester's screen.
"Yes, this is …" calls `POST /scans/{id}/confirm`, which adds the scan to that product's crowd reference.

## BLE contract, protocol v2 (for the ESP32 firmware)

Power comes from the iPhone's USB-C port; data goes over Bluetooth LE, because iOS apps can't read an
ESP32's USB serial without Apple's MFi program. Hardware per the wiring schematic: TCS34725 in line
(transmission, I²C bus 0 on GPIO 21/22), TSL2591 at 90° (scatter, I²C bus 1 on GPIO 16/17, since both
sensors use address 0x29), RGB LED on GPIO 25/26/27. GPIO 16/17 are taken by PSRAM on WROVER modules, so
use a WROOM-based board.

Nordic UART Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`, advertised. The app writes commands to RX
(`6E400002-…`); the tester answers with `\n`-terminated lines on TX (`6E400003-…`), `\r\n` is fine.

| App writes | Tester answers |
|---|---|
| `b` | `D,r,g,b,c,scatter` with the LED off, then `B,r,g,b,c,scatter` with the white LED on and clean water in the cuvette |
| `s` | `S,t_ms,r,g,b,c,scatter` once per second (60 s), then `E` |
| `L\|line1\|line2` | nothing; show the two lines on the tester's screen |

- `r,g,b,c` are raw TCS34725 counts, `scatter` raw TSL2591 counts. White = all three LED colors on.
- Keep gain and integration time fixed between blank and sample, and between runs.
- Send at least one line per second while working; the app gives up after 5 s of silence.
- Each line must fit one notification (the stub sets MTU 185; lines are about 50 bytes).

## Known shortcuts

- The crowd reference starts from simulated seed scans (`scripts/seed_demo.py`, marked synthetic). Replace
  them with about 5 real confirmed scans per demo product before judging.
- `backend/suppbuddy-backend/data/tainted_supplements.csv` ships empty; import FDA's list
  (`python -m scripts.import_tainted`) before the demo, or the tainted check is skipped.
- Scoring thresholds and record weights are first guesses; `grep -rn "TODO(" backend` lists them.
