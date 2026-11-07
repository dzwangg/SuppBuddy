# SuppBuddy backend

FastAPI server that turns a cuvette reading + a label photo into a three-part report:
**accuracy** (does this sample behave like other scans of the same product), **quality**
(dissolves cleanly, no excess filler), and **reputability** (FDA tainted list, recalls,
adverse events, NIH label registry). An optional Claude agent writes the plain-language summary.

Design borrowed from Peel (HackMIT 2026): staged pipeline, fast deterministic report first,
agent narrative second, every external stage can fail without killing the scan.

## Quick start

```bash
cd suppbuddy-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY for vision + agent (optional)
python -m scripts.seed_demo     # simulated reference scans so comparisons work today
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest -q                       # 23 tests, no network or key needed
```

Open http://localhost:8000/docs. Try `POST /dev/simulate?profile=vitamin_c_cornstarch` (should WARN)
vs `profile=vitamin_c` (should be CONSISTENT).

For the phone to reach your laptop on the same wifi use your LAN IP, or `ngrok http 8000`.

## How a scan flows

```
iPhone app ── POST /label/extract (photos) ──► LabelInfo (user confirms/edits)
          ── POST /scans {label, readings} ──► 202 {id, status: pending}
          ── GET  /scans/{id} (poll ~1 s) ───► partial (~1-3 s) ► complete (~15-45 s with agent)
          ── GET  /scans/{id}/lcd ───────────► {code, line1, line2} → forward to ESP32 LCD
          ── POST /scans/{id}/confirm ───────► user says "yes, this is that product" → feeds crowd DB
```

| Stage | File | What it does | Needs network |
|---|---|---|---|
| 0 features | `app/sensors/features.py` | QC, absorbance per band, scatter, t50/t90, noise | no |
| 1 product | `app/fingerprints.py` | normalize brand+name → product id | no |
| 2 deterministic | `app/pipeline.py` + `app/scoring/*` | tainted CSV, openFDA recalls + CAERS, NIH DSLD, crowd z-scores → verdict | yes (degrades) |
| 3 agent | `app/agent/harness.py` | Claude tool loop, writes headline/summary/citations | yes (optional) |

**The LLM never sets the verdict.** `scoring/verdict.py` decides; the agent only explains. Keep it that way: it's what makes the demo repeatable and the pitch honest.

## The sensor math (`app/sensors/features.py`)

```
A_c(t) = -log10( (I_c(t) - dark_c) / (blank_c - dark_c) )    c ∈ {R,G,B}   TCS34725, in line
S(t)   = (scatter(t) - dark_s) / (scatter_blank - dark_s)    1.0 = water   TSL2591, 90°
```

Fingerprint features: `A_R, A_G, A_B, ratio_BR, ratio_GR, S_final, t90_s, plateau_noise`.
Accuracy = RMS z-score vs. the product's confirmed scans (≤1.5 consistent, ≤3 borderline, else inconsistent).
Fewer than 3 scans → falls back to rough ingredient-class ranges in `data/class_references.json`.

QC rejects: <10 samples, saturated channel, dead LED (blank ≈ dark), flat signal (looks like water).
Only QC-passing, user-confirmed scans update a fingerprint.

## Device payload contract (agree with David)

```json
{
  "label":   { "brand": "...", "product_name": "...", "ingredients": [{"name": "...", "amount": 100, "unit": "mg"}], "lot": "..." },
  "readings": {
    "device_id": "esp32-01",
    "protocol": "v1",
    "led_mode": "white",                     // or "sequential_rgb"
    "tcs_gain": 4, "tcs_integration_ms": 154,
    "dark":  { "r": 300, "g": 320, "b": 280, "c": 900, "scatter": 40 },
    "blank": { "white": { "r": 18000, "g": 22000, "b": 15000, "c": 55000, "scatter": 400 } },
    "samples": [ { "t_ms": 0, "r": 17950, "g": 21900, "b": 14800, "c": 54000, "scatter": 410, "led": "white" } ]
  },
  "sample_prep": { "mass_mg": 100, "volume_ml": 3, "stirred": true, "form": "capsule_powder" }
}
```

`GET /dev/readings?profile=b_complex` returns a full example in exactly this shape.
In `sequential_rgb` mode, send one blank per LED (`"blank": {"r": {...}, "g": {...}, "b": {...}}`) and tag each sample's `led`.

## What to change once you know more

Every assumption is tagged in code. `grep -rn "TODO(" app scripts data` lists them all.

| Tag | Who to ask | File | What to change |
|---|---|---|---|
| `TODO(protocol)` | Akshay, Kevin | `app/schemas.py` | LEDs all-on vs. cycled R→G→B. Set `led_mode` default. |
| `TODO(protocol)` | Akshay, Kevin | `app/schemas.py` `SamplePrep` | Lock powder mass, water volume, stir, run length. **Most important item on this list.** Bump `protocol` to `v2` if it changes after you collect data; old fingerprints won't mix. |
| `TODO(protocol)` | Akshay, Kevin | `app/sensors/features.py` | Which LED drives the scatter reading in sequential mode (assumed green). |
| `TODO(hardware)` | Akshay, Kevin | `app/config.py`, `.env` | `TCS_SATURATION` / `TSL_SATURATION` from chosen gain + integration time (TCS max = min(65535, 1024 × cycles)). |
| `TODO(hardware)` | David | `app/schemas.py` | Firmware should report gain/integration so mismatched scans can be rejected. |
| `TODO(lcd)` | Trevor | `app/scoring/verdict.py` `lcd_message` | Display size (16×2 assumed) and wording. Codes: `TESTING CONSISTENT CHECK WARNING NO_REF BAD_SCAN`. |
| `TODO(calibrate)` | you, after scanning | `app/config.py` | z thresholds, `std_floor`, `turbidity_high`, `plateau_noise_high`. |
| `TODO(calibrate)` | you | `data/class_references.json` | Replace guessed ranges with real mean ± 3 std per class. |
| `TODO(calibrate)` | you | `scripts/seed_demo.py`, `app/sim.py` | Replace simulated seed scans with 5 real scans per demo product. |
| `TODO(calibrate)` | you | `app/scoring/reputability.py` | Point weights for recalls/CAERS/tainted. |
| `TODO(verify-api)` | you | `scripts/import_tainted.py` | Download FDA's tainted supplements list and import it. **`data/tainted_supplements.csv` ships empty.** |

## Fixed 2026-11-07

- `vision.py` and the agent's last-resort call forced `tool_choice`, which Claude Sonnet 5.5 / Opus 5.5 reject
  with a 400 (label reading failed every time). Vision now uses `messages.parse(output_format=LabelInfo)`;
  the agent is asked once more instead, then the deterministic report stands.
- `max_tokens` 1500/2000 left too little room now that thinking is always on; now 16000. Agent effort is
  `medium` (`AGENT_EFFORT`), timeout 90 s. Web search is `web_search_20260209`.
- Recalls: openFDA lists one record per bottle size and keeps recalls forever, so Nature Made scored 0/100.
  Now one penalty per recall event, weighted by age (full under 2 years, half under 5, then 10%), capped at
  40; a lot-number match is still added in full. CAERS counts barely move the score (they scale with sales).
- An empty tainted CSV counted as a checked source, so unknown products scored 70 "mixed"; now it's skipped.
- NIH lookup by name accepted another brand's same-named product; the brand must match now. Lookup by
  barcode (`label.upc`) is new, and a barcode registered to a different brand is a high-severity finding.
- LCD: "CONSISTENT" was cut to "CONSISTEN"; a crashed scan showed "Analyzing..." forever.
- `/label/extract` returns a 502 with the reason instead of a bare 500.

The iOS app now sends exactly the device payload below (white LED mode, 60 one-second samples).

## Before the demo

1. Fill `data/tainted_supplements.csv` (`python -m scripts.import_tainted export.csv`).
2. Run 5 real scans per demo product and confirm them. Delete `data/suppbuddy.db` first to drop the synthetic seeds.
3. Run each demo product once with wifi on to warm the openFDA/DSLD cache (24 h TTL, `CACHE_TTL_HOURS`). If venue wifi dies, set `EVIDENCE_OFFLINE=1`: cached lookups still work, uncached ones are marked skipped.
4. The money shot: genuine vitamin C → CONSISTENT, same powder + cornstarch → WARNING.

## Honest limits (say these on stage before a judge does)

Three broad color bands and one scatter channel cannot identify a compound or measure dose.
The device detects **deviation from other scans of the same product**. That's why the crowd DB is
the product. Reports say "consistent with N scans," never "verified."

## Layout

```
app/
  main.py            FastAPI routes
  config.py          every threshold and env var
  schemas.py         API contracts (device payload, label, report, LCD)
  db.py              SQLite/Postgres models
  pipeline.py        staged scan pipeline
  sensors/features.py   raw readings → QC + features
  scoring/           accuracy, quality, reputability, verdict + LCD text
  fingerprints.py    crowd reference stats (Welford)
  evidence/          openFDA, NIH DSLD, tainted CSV, cache
  agent/             Claude tool loop + tools
  vision.py          label photo → structured label
  sim.py             fake device for testing
scripts/  seed_demo.py, import_tainted.py
tests/    features, API flow, agent loop (fake client)
data/     class_references.json, tainted_supplements.csv, suppbuddy.db (created at runtime)
```
