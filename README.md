# SupPal iPhone app

SwiftUI app (iOS 17+). Flow: measure a water blank, measure the dissolved sample, photograph the label, Analyze.
Analyze sends the label photo, the absorbance spectrum and the closest database matches to Claude
(with web search for recalls, FDA warning letters, certifications) and shows the report.

## Run

1. `cp Secrets.example.xcconfig Secrets.xcconfig` and put your Anthropic API key in it (gitignored).
2. Open `SupPal.xcodeproj`, pick a simulator or your iPhone, Run.
   On a real iPhone, set your team under Signing & Capabilities first.

The Simulator has no Bluetooth or camera, so there the app uses a simulated tester and the photo library.
After editing `project.yml`, regenerate with `xcodegen generate`.

Logic check (BLE parsing, absorbance, matching, report parsing):

```bash
swiftc SupPal/Analysis.swift SupPal/Agent.swift SupPal/NIH.swift checks/main.swift -o /tmp/suppal-check && /tmp/suppal-check
```

## BLE contract (for the ESP32 firmware)

Power comes from the iPhone's USB-C port; data goes over Bluetooth LE, because iOS apps can't read an
ESP32's USB serial without Apple's MFi program.

| | |
|---|---|
| Service | Nordic UART `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`, advertised |
| RX (app writes) | `6E400002-…`: the app writes `m` to request one measurement |
| TX (ESP32 notifies) | `6E400003-…`: one line of raw channel intensities, comma-separated, ending in `\n` (`\r\n` is fine), e.g. `3100,3400,3650,3900,4100,4000,3800,3500` |

- Send raw counts (higher = more light). The app computes absorbance against the blank.
- Same channel count and order every time. The demo database has 8 channels; the real database must match the sensor.
- Answer within 5 s. A line can be split across notifications; the app reassembles it.

`firmware-stub/suppal_stub/suppal_stub.ino` implements this with fake readings, so you can test the app against a
bare ESP32 (Arduino IDE, ESP32 board package). The app connects to the first tester it finds.

## Known shortcuts

- The API key is compiled into the app. Fine for a demo; move the Claude call behind a server before
  sharing the app beyond the team.
- `SupPal/references.json` is placeholder data (marked "(demo)"), not real measurements. Replace it with the
  team's crowdsourced database.
- Matching is cosine similarity on a few channels: good for "does this look like the reference", not proof of identity or purity.
