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
pytest -q                       # 36 tests, no network or key needed
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
A_c(t) = -log10( (I_c(t) - dark_c(t)) / (blank_c - dark_c) )   c ∈ {R,G,B}   TCS34725, in line
S(t)   = (scatter(t) - dark_s(t)) / (scatter_blank - dark_s)   1.0 = water   TSL2591, 90°
```

Protocol v3 ("cycle" mode) takes a dark reading and one reading each under white, red, green and blue light
every ~1.4 s, and the backend uses all of it:

| Feature | From | Tells you |
|---|---|---|
| `A_R, A_G, A_B` | each colored LED through its matching channel (white light if that LED is too dim) | color |
| `ratio_BR, ratio_GR` | the same | color shape, independent of how much powder went in |
| `S_final` | white light, side sensor | cloudiness at the end: fillers, undissolved powder, natural protein haze |
| `t90_s`, `plateau_noise` | white light, in-line sensor | dissolving speed; clumps or bubbles |
| `scatter_exp` | blue vs red LED, side sensor | particle size: fine haze (protein) scatters blue much more (2-4); coarse grains (starch, flour) scatter every color alike (~0) |
| `S_residual` | white light, side sensor | share of the peak cloudiness still there at the end: soluble powder ~0, insoluble filler ~1. A ratio, so the scoop size barely moves it |
| `settle_rate` | white light, side sensor | solids still sinking at the end |
| `S_noise` | white light, side sensor | scatter flicker: grains drifting through the beam |

Dark readings during the run are interpolated and subtracted at each reading's time (room-light drift), and
`sample_prep` mass/volume rescale the color and cloudiness features to the standard 500 mg in 50 mL.

**Accuracy** = z-scores vs. the product's confirmed scans: the worse of the RMS over all features (≤1.5
consistent, ≤3 borderline) and the largest single feature (>3.5 borderline, >5 inconsistent), so a filler that
mostly moves cloudiness isn't averaged away by the color features. Fewer than 3 scans → falls back to rough
ingredient-class ranges in `data/class_references.json` (now including creatine).

**QC rejects:** <10 samples, a saturated channel (limits derived from the integration time the tester reports),
dead LED (blank ≈ dark), light leak (a dark reading climbing during the run), flat signal (looks like water).
Warnings: a dim colored LED (white light used for that band), infrared rising, sensor settings different from
the reference settings, sample prep far from the standard.

**Crowd data:** only QC-passing, user-confirmed scans update a fingerprint. Once a product has 3+ scans, a
confirmed scan that's inconsistent with them is **held** (`{"held": true}`) instead of merged; send
`{"force": true}` to merge it after review. Products are keyed by **barcode** (valid GTIN check digit) when
there is one, otherwise brand + name + **flavor**.

## Device payload contract

```json
{
  "label":   { "brand": "...", "product_name": "...", "flavor": "...", "upc": "...", "ingredients": [{"name": "...", "amount": 100, "unit": "mg"}], "lot": "..." },
  "readings": {
    "device_id": "esp32-SuppBuddy",
    "protocol": "v3",
    "led_mode": "cycle",
    "tcs_gain": 4, "tcs_integration_ms": 50, "tsl_gain": 25, "tsl_integration_ms": 100,
    "dark":  { "r": 300, "g": 320, "b": 280, "c": 900, "scatter": 40, "ir": 20 },
    "blank": { "white": { "r": 6000, "g": 7000, "b": 5000, "c": 18855, "scatter": 400, "ir": 30 },
               "r": {...}, "g": {...}, "b": {...} },
    "samples": [ { "t_ms": 0,   "led": "off",   "r": 301, "g": 321, "b": 279, "c": 901, "scatter": 41, "ir": 20 },
                 { "t_ms": 285, "led": "white", "r": 5950, "g": 6930, "b": 4900, "c": 18600, "scatter": 610, "ir": 31 } ]
  },
  "sample_prep": { "mass_mg": 500, "volume_ml": 50, "stirred": true }
}
```

`GET /dev/readings?profile=b_complex` returns a full example in exactly this shape. The older `white` and
`sequential_rgb` modes are still accepted.

## What to change once you know more

Every assumption is tagged in code. `grep -rn "TODO(" app scripts data` lists them all.

| Tag | Who to ask | File | What to change |
|---|---|---|---|
| `TODO(protocol)` | Akshay, Kevin | `app/config.py` `sample_mass_mg` / `sample_volume_ml` | Confirm the standard prep (500 mg in 50 mL). **Most important item on this list.** Bump `PROTOCOL_VERSION` (v3 → v4) if it or the firmware's settings change after you collect data; old fingerprints won't mix. |
| `TODO(calibrate)` | you, after scanning | `app/config.py` | `min_excess_scatter`, `residual_high`, `coarse_scatter_exp`, `settle_high`, `scatter_noise_high`, `light_leak_frac`: first guesses checked only on simulated data. |
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
