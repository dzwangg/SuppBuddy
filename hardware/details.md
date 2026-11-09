# SuppBuddy: technical documentation

This file records every CAD/hardware iteration and every hardware component. Update it with every
change (date, version, what changed and why, how it was checked).

- **Units:** mm unless noted.
- **Model axes:** X = length (left→right), Y = depth (front→back), Z = up. The origin is the outer
  front-left-bottom corner of the base. "Front" is the face nearest the vial.
- **Where numbers come from:** "measured" means the team measured the real part. "Listing",
  "datasheet" or "drawing" names the source. "Assumed" means nobody has checked it yet.
- **Dates** are local time (UTC−5).
- **Last updated:** 2026-11-08.
  - Earlier in the day: a documentation review, then a second fact-check.
  - Evening: each iteration got its own Part Studio, and V3 was rebuilt as an ordinary feature tree
    with identical geometry (§2, §3).

**Contents**

1. [System summary](#1-system-summary)
2. [Onshape document and tooling](#2-onshape-document-and-tooling)
3. [Iteration history](#3-iteration-history) (V1, V2, V3)
4. [V3 parameter reference](#4-v3-parameter-reference)
5. [Hardware components](#5-hardware-components)
6. [Optics design notes](#6-optics-design-notes)
7. [Printing and assembly (V3)](#7-printing-and-assembly-v3)
8. [Open items and things to measure](#8-open-items-and-things-to-measure)
9. [Presentation graphics](#9-presentation-graphics)

Appendices: [A. V1 and V2 variable tables](#appendix-a-v1-and-v2-variable-tables) ·
[B. Input and decision log](#appendix-b-input-and-decision-log) ·
[C. Document history](#appendix-c-document-history)

---

## 1. System summary

SuppBuddy is a small at-home tester for dietary supplements. The user dissolves a sample in water in
a clear 20 mL vial and drops the vial into the device. An ESP32 lights four LEDs (red, green, yellow,
IR) one at a time through the vial. Two light sensors measure the result:

- **TSL2591 at 180°:** transmitted light, so absorbance per LED.
- **TCS34725 at 90°:** side-scattered light, which indicates turbidity or undissolved filler.

The phone app combines these readings with a photo of the label, a crowdsourced database of other
users' results and brand-reputation lookups, and an AI agent (Claude API) writes the verdict. The
phone powers the device over USB-C. The phone link is still open: BLE is the likely choice
(see §5.2).

### 1.1 Scope of this document

- It covers the enclosure CAD and the hardware. On 2026-11-07 the team asked for CAD only in this
  repo for now; teammates are building the firmware, phone app, database/backend and agent. Their
  open decisions (phone link, app stack, where the backend lives, sample prep) are listed in
  CLAUDE.md.
- Hardware facts the firmware side needs are still recorded here: the USB-C power caveat (§5.2), LED
  drive (§5.3), the I2C address clash (§5.6) and the measurement routine (§6).

### 1.2 Original design brief (2026-11-07)

V1 was built from this brief. It's paraphrased here. The full text was in a `prompt` file at the old project root, which has since been deleted.

- **Parts:** three standard LEDs (red, green, yellow) and an infrared emitter, a standard ESP32
  (the brief's "esp32D") and an LCD, all plugged into one breadboard. Two light sensors: a TCS34725 RGB
  sensor (the brief named the CJMCU-34725 board) and a TSL2591 lux sensor, to capture how light
  passes through the sample.
- **Enclosure:** a HackMIT Peel-style container around the breadboard, with the USB-C port exposed.
  The LCD is wired to the breadboard and shows on the outside. A cuvette sits in the centre: the user
  puts it in and puts a lid on for the test. The light sensors sit across the cuvette from the LEDs.
- **Data:** the ESP32 sends the readings to the user's phone.
- **CAD requirements:** a small container that is simple, editable and quick to print, with no
  complicated shapes. Parametric, using Onshape variables.

**What changed since:**
- The cuvette became an SKS vial in V3 (§3).
- The TCS34725 board is the Adafruit #1334 (§5.5). The TSL2591 board is an EC Buying breakout (§5.4).
- "Parametric" is met by Part Studio variables in V1/V2. The original V3 used one FeatureScript
  feature with 69 named parameters (§4). The current V3 feature tree (2026-11-08) has 19 Part Studio
  variables for the fits and measure-before-printing sizes (§3).
- Every part prints without supports (§7).

---

## 2. Onshape document and tooling

| Item | ID / value | Notes |
|---|---|---|
| Document | **SuppBuddy** `ada0757f8a367ed8c935f14f` | EDU Standard account |
| Workspace | Main `389f688fe28c85a3add01f94` | |
| DeviceHolder V1 | `ec235d284e5de6ef932eea1f` | Copy of Part Studio 1 at version V1: 77 features, full history |
| DeviceHolder V2 | `3357f3a35745cfbcf17b731f` | Copy of Part Studio 1 at version V2: 119 features, full history |
| **DeviceHolder V3** | `45284f49e09add42eb3ea0fc` | **Current model.** Ordinary feature tree, 77 features (19 variables + 58), built by `cad/build_v3.py` |
| DeviceHolder V3 (FeatureScript, old) | `5da49a2f1204f18bc3cad3cc` | The old "Part Studio 1". One feature: "SuppBuddy enclosure v3" (`F9fAx1YzT7Xsu9t_0`). Same geometry as DeviceHolder V3. Delete it by hand once "v3 drawings" is moved off it |
| v3 drawings | `5d020a670837d65284758668` | Onshape Drawing, made by hand in Onshape. References the old FeatureScript studio |
| Feature Studio | "SuppBuddy FeatureScript" `7099a3d894bf571a905f8e09` | FeatureScript std 3112. Generated by `cad/build_fs.py`; don't hand-edit. Only the old studio uses it |

**State of Main (2026-11-08, evening):**
- Assembly 1, its BOM and the zz_api_probe tab were deleted by hand.
- Part Studio 1 was renamed "DeviceHolder" by hand. Its drawing, "v3 drawings", was added the same
  way.
- **Each iteration now has its own Part Studio** (asked for on 2026-11-08).
  - V1 and V2 are full copies of their versions. The copy endpoint (`elements/copyelement`) only
    accepts a workspace as its source; a version ID returns 404. So for each one:
    1. Branch a workspace from the version.
    2. Copy Part Studio 1 from that branch.
    3. Rename the copy through the metadata API.

    Both copies regenerate with all features OK.
  - **Two branches are left over**, because the API key can't delete workspaces (403): "tmp V1
    source (delete me)" `4e76985185b254e87ed1a942` and "tmp V2 source (delete me)"
    `1757c9b922bcbe80e0247e4d`. Delete them by hand in the version graph.
  - V3 was rebuilt as an ordinary feature tree (§3, "V3 rebuilt as a feature tree").
- **Tab order** from the API: old FeatureScript studio, V2, V1, v3 drawings, FeatureScript tab, V3.
  The copies landed next to their source tab, not at the end, so drag V1 and V2 into order by hand.
- The default planes are hidden in the old studio (asked for on 2026-11-07). The new studios have
  their own plane features.

### Versions

| Version | Onshape version ID | Date | Built by | Summary |
|---|---|---|---|---|
| Start | `295a9ce29651299ef03c467c` | 2026-11-06 | — | empty document |
| **V1** | `a1943da801aa6809c9a6293d` | 2026-11-07 | `cad/build_enclosure.py` (v1 revision) | cuvette box, 77 features |
| **V2** | `6df030666e7f9f1402087bf2` | 2026-11-07 | `cad/build_enclosure.py` (current file) | inserts, LCD light seal, light wall, rounded cap, 119 features |
| **V3** | `b4de7f1d731ede50c02bbeee` | 2026-11-07 | `cad/build_fs.py` | SKS vial, cap sleeve, vertical LED column, sensor pockets; 1 FeatureScript feature, 69 parameters |

- **Open a version by link:**
  `https://cad.onshape.com/documents/ada0757f8a367ed8c935f14f/v/<version ID>/e/5da49a2f1204f18bc3cad3cc`.
  `onshape_version.py` prints this link when it creates a version.
- **In Onshape:** open the Versions and history panel (clock icon). An old version can be brought
  back into Main with **Restore**, but that replaces the current workspace state.

### Scripts (`cad/`)

Run the Onshape scripts with the MCP's virtual environment, for example
`onshape-mcp/.venv/Scripts/python.exe cad/build_fs.py`. They read the API keys from
`onshape-mcp/.env`.

| File | What it does |
|---|---|
| `build_v3.py` | **Current V3 builder (2026-11-08).** Builds V3 as an ordinary feature tree in a new Part Studio, "DeviceHolder V3": 19 variables (`VARS`) plus 58 planes, sketches, extrudes and fillets. Defaults come from `GROUPS` in `build_fs.py`. About 80 API calls and no FeatureScript-eval calls: planes, boolean scopes and fillet edges are picked with query strings. It records what it built in `.v3_state.json` and resumes from it. `--dry` lists the features. |
| `.v3_state.json` | Element ID and feature IDs that `build_v3.py` created. |
| `build_fs.py` | **The FeatureScript V3 model** (now in "DeviceHolder V3 (FeatureScript, old)"). Generates the FeatureScript (parameter table `GROUPS` plus geometry `TEMPLATE`), pushes it to the Feature Studio, and adds or updates the single feature in that studio. About 4 API calls per run. `--dry-run` only writes `suppbuddy_enclosure.fs`. `--set name=value ...` applies one-off values. |
| `suppbuddy_enclosure.fs` | Generated copy of the FeatureScript, for reading and diffing. Don't edit. |
| `.fs_state.json` | Feature Studio element ID and feature ID that `build_fs.py` updates in place. |
| `build_enclosure.py` | The v2 builder (sketch + extrude per feature over REST, about 150 calls). Kept as the record of how V2 was made. It refuses to run while Part Studio 1 has features. Its `--wipe` option used `.build_state.json`, which is gone. The v1 revision of this script and the abandoned v3 REST revision weren't kept, because the project isn't under version control. V1 itself survives as the Onshape version, with its variables in Appendix A. |
| `osh.py` | REST helpers: Onshape client with 429 back-off, BTM builders for variables, offset planes, fully constrained sketches, extrudes and fillets. |
| `onshape_version.py` | Creates a named Onshape version and refuses duplicates. Usage: `onshape_version.py V4 "description"`. It takes the document IDs from `build_enclosure.py`. |
| `render/` | Presentation graphics from the V3 geometry: STL export, Blender scene and a line-drawing engine. See §9. |

### Onshape API limits (hit on 2026-11-07)

- Limits are **per user, per endpoint**, over long (about daily) windows. The `x-rate-limit-remaining`
  header shows what's left.
- After the v1/v2 builds and verification, the FeatureScript-eval endpoint
  (`POST /api/v8/partstudios/.../featurescript`) returned 429 with `Retry-After: 78281` (about
  21.7 h).
  - The REST builder needs this endpoint: `osh.py` `fs()` uses it to find the edges and faces it has
    just made and to check bounding boxes.
  - Budgets left on other endpoints right after: `/features` 78, `/bodydetails` 500, `/parts` 500,
    `/versions` 1000.
- The team suggested using Onshape in their logged-in browser instead. That's good for viewing the
  model and reading feature errors, but it doesn't get around the limit:
  - REST calls made from the tab (`fetch`) count against the **same** per-user quota (the counter
    dropped from 78 to 77 on one call);
  - a FeatureScript POST from the tab returned 401. The likely cause is a missing XSRF token; that
    wasn't tried.
- This is why v3 moved to FeatureScript. The model regenerates inside Onshape, so a rebuild is about
  4 calls instead of about 150, and nothing needs the eval endpoint.
- FeatureScript rule learned the hard way: all operations under one Id prefix must be **contiguous**
  in the operation history. For example, `id + "bp" + "outer"`, then a fillet, then
  `id + "bp" + "post0"` fails with "Parent Id ... used at two non-contiguous points".

---

## 3. Iteration history

### V1: cuvette box (2026-11-07)

Built with `build_enclosure.py` (v1 revision) from the brief in §1.2: 77 features, 43 Part Studio
variables plus 34 geometry features (sketches, extrudes, offset planes, fillets).

| Part | Bounding box (min → max) | Notes |
|---|---|---|
| Base | (0, 0, 0) → (92, 93, 48) | 92 × 93 × 42 box; the cuvette chamber collar rises to z = 48 (4 mm above the lid) |
| Lid | (0, 0, 42) → (92, 93, 44) | flat 2 mm plate |
| Cuvette cap | (28.1, 6.6, 44) → (57.4, 29.4, 61) | rectangular cup 29.3 × 22.8 × 17, inside 25.3 × 18.8 × 15 |

- **Chamber:** x 30.4–55.1, y 8.9–27.1, from the floor to z = 48.
- **Cuvette:**
  - Pocket 13.2 × 13.2 (12.5 + 2 × 0.35), 35 deep from the chamber top.
  - The cuvette bottom sits at z = 13, 11 mm above the floor.
  - Beam at z = 28, 15 mm above the cuvette bottom, so about 2 mL of sample covers it.
  - The cuvette sticks up 10 mm above the chamber so it can be grabbed.
- **LEDs:** 2 × 2 grid of ⌀5.2 holes at 6.5 pitch in a 9 mm wall on the −X side.
  - The LEDs sit fully inside the wall, so they can't touch the cuvette.
  - They're wired to the breadboard with jumpers.
- **Sensor windows:** 8 × 8, at 180° (+X) and 90° (+Y).
  - Each sensor board is about 20 mm wide, but a cuvette face is only 12.5 mm, so the two boards
    can't both sit opposite the LEDs.
  - The TSL2591 takes the 180° window because the TCS34725's IR-blocking filter can't see the IR LED.
    The TCS34725 goes at 90°.
- **USB-C:** cutout 13 × 8 in the left wall at y 55–68, z 12–20 (centre on the breadboard centre line,
  y = 61.5). `usb_z` = 14 was a guess at the port height.
- **Lid:** chamber hole (+0.3 per side), LCD window 72 × 25, 4 × ⌀3.2 LCD holes at 75 × 31.
- **No fasteners:** the lid was located only by the collar.
- **Checked:** all 77 features regenerated. A test with a different breadboard length and interior
  height moved the box, chamber, holes, lid and cap correctly, then the defaults were restored.

**Team feedback on V1 (2026-11-07):** keep the LED mounting, which the team liked, save the model as
V1, then for V2:
- add M3 heat-set inserts at the lid corners. The team's inserts measure about 0.19 in OD and
  0.15 in tall; size the holes to the usual standard for them;
- make the cap a rounded shape that's easy to grab and move, not a plain box;
- fit the LCD well enough that no light gets in around it;
- add a wall so light coming in at the USB port can't reach the optics;
- get ready for better sensor and LED mounts once their specs arrive (this became V3).

**Problems that led to V2:**
- The standard 1602 bezel is 71.3 × 26.3, so the 25 mm-tall window was too small.
- The lid had no fastening.
- Light could leak in around the USB-C plug and the LCD.
- The cap was a plain box.

### V2: inserts, LCD light seal, light wall, rounded cap (2026-11-07)

Built with `build_enclosure.py` (current file): 119 features, 67 variables plus 52 geometry features,
all OK.

| Part | Bounding box (min → max) | Size |
|---|---|---|
| Base | (0, 0, 0) → (92, 103.6, 48) | 92 × 103.6 × 48 |
| Lid | (0, 0, 35.4) → (92, 103.6, 44) | 92 × 103.6 × 8.6 (2 mm plate + 6.6 mm LCD seal) |
| Cuvette cap | (27.1, 5.6, 44) → (58.4, 30.4, 69) | 31.3 × 24.8 × 25 (cup 18 + knob 7) |

**Changes from V1:**
- **Lid screws:** 4 corner posts (9 × 9, full height) with M3 heat-set insert holes (⌀4.2, 7 deep).
  The lid has 4 × ⌀3.4 clearance holes. Screws are M3 × 6.
- **Light wall:** 1.6 mm wall between the optics zone and the electronics bay, with a 24 × 10 mm wire
  notch at the top. Light leaking in around the USB-C plug can't reach the optics.
- **LCD window:** 71.8 × 26.8 (bezel 71.3 × 26.3 + 0.25 per side).
- **LCD light seal:** under the lid, a 1 mm ledge plus a 1.6 mm skirt around the 80 × 36 PCB (+0.3
  per side).
  - The PCB is pulled up against the ledge by 4 × M2.5 × 12 screws and nuts (lid holes ⌀2.8 at
    75 × 31).
  - The only light path is the snug bezel window, which the bezel itself fills.
- **Cap:** vertical corners rounded r5, top roundover r3, knob ⌀12 × 7 with r2 roundover.
- **Unchanged from V1:** the cuvette chamber and pocket, the 2 × 2 ⌀5.2 LEDs, the 8 × 8 windows and
  USB-C.

**Verification:**
- No interference between any two parts (FeatureScript `evCollision`). Base/lid and lid/cap only
  touch.
- Parametric test with `bb_len` 120, `in_h` 50, `lcd_bz_t` 9 and `knob_d` 10: all 119 features
  regenerated OK.
- The team approved V2 on 2026-11-07 ("This all looks good") and switched to vials in the same
  message.

**Problems that led to V3:**
- The team switched from cuvettes to round SKS 20 mL vials (§5.8).
- The LEDs were re-measured at 4.6 mm body / 5.3 mm lip, so the 5.2 holes were wrong. A first reading
  of 0.12 in / 0.15 in (3.05 / 3.81) was corrected the same day.
- A 2 × 2 grid gives unequal path lengths through a round vial (§6). The team spotted this and
  suggested lining the LEDs up vertically.
- There was nothing to hold the sensor boards. The team suggested heat-set inserts "if needed" and
  asked for that work to go into V3, not V2.

### V3: SKS vial, cap sleeve, vertical LED column, sensor pockets (2026-11-07)

Built with `build_fs.py` as **one custom FeatureScript feature** with 69 parameters, all in mm. To
edit it in Onshape, double-click "SuppBuddy enclosure v3", change values (they're in collapsible
groups), and press ✓. Everything below is at default parameters.

**Team decisions (2026-11-07):**

| Question | Options considered | Chosen | Why |
|---|---|---|---|
| Light seal with a vial | (a) a printed sleeve pressed onto the vial's white cap, its skirt over a collar; (b) the vial top sticks out above the lid and a separate rounded cap goes over it. Both ideas came from the team. | (a) printed cap sleeve | The vial goes in and comes out in one motion, and the dark sleeve also blocks light coming through the white cap. Costs one fit-test print. |
| LED layout | 2 × 2 grid, or one vertical column | vertical column on the vial axis plane | Every beam crosses the same amount of liquid (§6). |
| V3 scope | vial + LEDs + sensor mounts, or vial + LEDs only | vial + LEDs + sensor mounts | The round bore meant redesigning the optics block anyway. |
| Sensor-board mounting | slide-in pockets; M2/M2.5 screws into printed bosses; heat-set inserts (the board holes look about 2.5 mm, so M2.5 inserts, and the M3 screws wouldn't pass) | slide-in pockets | No screws, quick to print, and the pocket walls block side light. |
| Vial size | estimates (body 25.4, about 58 tall, cap about 24 × 11) or caliper numbers | calipers: body 27.4, cap 24.7, 60 tall with the cap | The cap height wasn't given, so `vcap_h` = 10 is assumed. |

**How V3 was built (2026-11-07):**
1. A v3 revision of the REST builder (`build_enclosure.py`, 91 variables) was checked offline: every
   expression evaluated and the layout fitted inside the walls. It then ran with `--wipe`, which
   deleted V2's 119 features from Part Studio 1.
2. The rebuild then stopped on a 429 from the FeatureScript endpoint, with `Retry-After` 78,281 s
   (about 21.7 h; §2). `osh.py` retries a 429 for about 3 minutes (2 s back-off, doubling to 60 s),
   which can't outlast a wait that long.
   - Afterwards Part Studio 1 had no features at all, and it stayed empty until step 3.
   - V2 was never at risk: it's a saved version.
3. The v3 REST revision was dropped, and `build_enclosure.py` was put back to the exact file that
   built V2. The enclosure was then rewritten as one FeatureScript feature (`build_fs.py`). That's
   about 4 API calls per rebuild, none of them on the eval endpoint.
4. The first push compiled, but the feature failed to regenerate.
   - Onshape shows that error only in the browser (FeatureScript notices panel): "Parent Id ... used
     at two non-contiguous points".
   - The fix: track each part as the union of the bodies made under its own Id prefixes (§2).
5. After the checks below, it was saved as version V3.

| Part | Part ID | Bounding box (min → max) | Size | Solid volume |
|---|---|---|---|---|
| Base | `JHD` | (0, 0, 0) → (92, 128.5, 51) | 92 × 128.5 × 51 (rim at 42, collar to 51) | 106.9 cm³ |
| Lid | `RICD` | (0, 0, 35.4) → (92, 128.5, 44) | 92 × 128.5 × 8.6 (2 mm plate + LCD seal) | 21.9 cm³ |
| Vial cap sleeve | `RDDD` | (27.1, 2.7, 45.5) → (64.9, 40.5, 65) | ⌀37.8 × 19.5 | 11.2 cm³ |

The volumes are solid volumes. At 100 % PLA (1.24 g/cm³) that's 133 g, 27 g and 14 g as an upper
bound; real prints with infill are lighter.

**What changed and why:**

1. **Cuvette → SKS 20 mL vial.**
   - Round bore ⌀28.2 (vial 27.4 + 0.4 per side), axis at (46, 21.6).
   - The bore runs from the floor top (z = 2, where the vial bottom rests) to the collar top
     (z = 51), 49 mm deep.
   - The collar (⌀33.2, 2.5 wall) rises 7 mm above the lid top (44 → 51).
2. **Vial cap sleeve** replaces the cuvette cap.
   - It is a printed cup that presses onto the vial's white cap: pocket ⌀24.8 = cap 24.7 + 0.1, with
     10 mm of grip.
   - It has a 3 mm roof and a 1.5 mm top roundover.
   - It has no knob. The option the team chose described "a knob on top", but V3 was built as a
     plain cylinder that you lift by its sides (§8).
   - Lifting the sleeve pulls the vial out with it.
   - With the vial seated, the sleeve's skirt (inner ⌀33.8, 2 mm wall) hangs over the collar
     (0.3 mm gap per side, 5.5 mm overlap). It stops 1.5 mm above the lid, so the vial bottom (not
     the sleeve) sets the height.
   - Light has to go up the 0.3 mm gap, over the collar top (1 mm gap), and down the 0.4 mm gap
     around the vial. With dark filament that's a light-tight labyrinth.
3. **LEDs in a vertical column on the vial axis plane** instead of a 2 × 2 grid. Every beam crosses
   the full vial diameter at normal incidence (§6).
   - 4 × ⌀4.8 holes, 5 deep, pushed in from the −X face (x = 22.9) of the optics block. The LED body
     is 4.6 and the 5.3 lip stops it at the face.
   - Centres at z = 11, 17, 23, 29: 9, 15, 21 and 27 mm above the vial bottom, 6 mm pitch.
   - A vertical **slit aperture** 2 wide × 22.8 tall (z 8.6–31.4) runs from the hole bottoms
     (x = 27.9) into the bore. Light enters the bore only through this 2 mm strip centred on the axis
     plane, which cuts stray light, while all four LEDs can still reach the single 180° sensor.
4. **Sensor windows** shrunk to 5 × 5, centred on the beam (z = 20). Each crosses the 2.5 mm block
   wall:
   - 180°: x 60.1–62.6 at y = 21.6.
   - 90°: y 35.7–38.2 at x = 46.
5. **Slide-in sensor pockets.** Each board slides down, chip facing the vial, header edge up, into
   C-shaped rails. The parts:
   - a 2.0 mm slot for the board (0.3 per side at the edges);
   - 1.5 mm of clearance in front for the board's parts, with the rails overlapping 1 mm of each
     board edge;
   - an open back for the header;
   - a solid stop under the board that puts the chip on the beam;
   - rails that end 4 mm below the board's top edge so the header pins are free.

   | Pocket | Block x | Block y | Block z | Slot | Board bottom stop | Chip height |
   |---|---|---|---|---|---|---|
   | TSL2591, 180°, on +X face | 62.6–67.3 | 11.8–31.4 | 2–25.5 | x 64.1–66.1, y 13.3–29.9 | z 10.5 | z 20 |
   | TCS34725, 90°, on +Y face | 34.0–58.0 | 38.2–42.9 | 2–26.0 | y 39.7–41.7, x 35.5–56.5 | z 9.6 | z 20 |

   - The TCS34725 board's back faces the electronics bay (its chip faces the vial). `tcs_room` = 16 mm
     behind it (to the light wall at y = 58.9) leaves room for header pins plus jumper plugs.
   - The TSL2591 has 22.7 mm behind it (to the right wall).
   - The LED leads have 20.9 mm (from the −X face to the left wall).
6. **Box re-laid out around the vial.**
   - The optics zone is now 56.9 deep: front gap 3 + bore 28.2 + 2 walls of 2.5 + pocket 4.7 +
     `tcs_room` 16.
   - The base grew to 92 × 128.5. The breadboard bay is y 60.5–117.5, x 2–90, with the breadboard
     centred at (46, 88).
   - The light wall is at y 58.9–60.5, with the wire notch x 34–58, z 32–42.
   - USB-C cutout: left wall, y 81.5–94.5, z 12–20 (centre 14 above the floor).
7. **Kept from V2:**
   - M3 insert posts (holes at (6.5 | 85.5, 6.5 | 122)).
   - Lid screw holes ⌀3.4.
   - The LCD light seal: window 71.8 × 26.8 at (46, 88); ledge opening 78 × 34 (z 37–42); PCB pocket
     80.6 × 36.6 (z 35.4–37); outer skirt 83.8 × 39.8.
   - LCD screw holes ⌀2.8 at (8.5 | 83.5, 72.5 | 103.5).
   - The light wall and the outer corner radius 4.

**Verification (2026-11-07):**
- The feature regenerates with status OK and no FeatureScript notices. Part names are set by the
  feature.
- Every cylindrical face was read back over REST `bodydetails`:
  - Base: bore ⌀28.2 and collar ⌀33.2 at (46, 21.6); LED holes ⌀4.8 with X axis at y = 21.6 and
    z = 11/17/23/29; inserts ⌀4.2 × 4; outer corners r4.
  - Lid: collar hole ⌀33.8, screw holes ⌀3.4 × 4, LCD holes ⌀2.8 × 4.
  - Sleeve: ⌀37.8 outside, ⌀33.8 skirt, ⌀24.8 cap pocket, plus the top roundover (torus).
- Parametric test with `vial_d` 30, `beam_h` 20, `tcs_room` 6, `bb_len` 120 and `vial_dx` +5
  regenerated OK.
  - The box became 128 × 121.1 and the bore ⌀30.8 at (69, 22.9).
  - The LEDs moved to z = 13/19/25/31 and the sleeve became ⌀40.4.
  - Reverting to defaults restored the original boxes exactly.
- **Part-to-part interference** couldn't be checked in Onshape (the eval quota was used up). It was
  checked on 2026-11-08 from the exported STLs (§7) instead, by scanning vertical columns 0.25 mm
  apart through each pair of parts:
  - no overlaps anywhere;
  - base and lid only touch (the lid plate on the rim and posts);
  - lid and sleeve are 1.5 mm apart;
  - a control run with the lid moved down 0.3 mm and the sleeve sideways 0.4 mm did flag both.

  The designed clearances: collar/skirt 0.3, collar/lid hole 0.3, sleeve/lid 1.5, collar top/sleeve
  ceiling 1.0. The LCD seal clears the base's inner features.
- Geometry re-check (2026-11-08): 112 probe points inside and just outside every hole, slot, pocket,
  wall and window listed in this section, tested against the exported STLs, all matched. The STL
  bounding boxes and volumes match the table above.
- Checked by eye in the browser: base internals (posts, light wall and notch, optics block, both
  pocket rail profiles), lid top (window, holes), and the sleeve seated on the collar.

#### V3 rebuilt as a feature tree (2026-11-08)

The team asked for V3 as "a proper cad instead of the featurescript thing", built with as few API
calls as possible. `cad/build_v3.py` rebuilds it in a new Part Studio, "DeviceHolder V3"
(`45284f49e09add42eb3ea0fc`), as an ordinary Onshape feature tree. The old one-feature studio is
kept, renamed "DeviceHolder V3 (FeatureScript, old)", because "v3 drawings" references it.

- **Variables (19):**
  - print and fit: `wall`, `floor_t`, `lid_t`, `fit`, `corner_r`;
  - vial: `vial_d`, `vial_fit`, `vcap_d`, `vcap_h`, `vcap_fit`;
  - LEDs and windows: `beam_h`, `led_d`, `led_depth`, `led_pitch`, `slit_w`, `win`;
  - things to measure: `tsl_sz`, `tcs_sz`, `usb_z`.

  Every other §4 value is a number inside the sketch and extrude expressions, so changing one means
  editing that feature. Derived sizes are written out as expressions of the variables. For example,
  the bore is `#vial_d + 2 * #vial_fit`, so changing `vial_d` moves the bore, collar, sleeve, box
  depth and sensor pockets together.
- **The tree (58 features after the variables):**
  - **Base:**
    1. Outline sketch, extrude and corner fillets.
    2. Rim plane, then the cavity cut.
    3. Floor plane, then one sketch with the 4 posts, the light wall and the optics block, added
       together.
    4. Collar, then the two sensor pockets.
    5. Cuts: insert holes, wire notch, vial bore, LED holes (LED plane), slit (slit plane), the 180°
       and 90° windows (each on its own plane), the TSL2591 and TCS34725 slot cuts (slot, front
       relief and back opening in one sketch each, on a plane at the board's bottom edge), and the
       USB-C cutout.
  - **Lid:**
    1. Outline, extrude and corner fillets.
    2. LCD seal skirt and ledge, each a ring added down from the rim.
    3. One cutout sketch: bezel window, collar hole, 4 LCD holes and 4 screw holes.
  - **Sleeve:**
    1. Bottom plane, outline and extrude.
    2. Top roundover.
    3. Skirt bore and cap pocket.
  - All sketches are fully dimensioned from the origin.
- **Differences in construction, not in shape:**
  - The cavity's inner corner rounding (r2 in the FeatureScript) is left out. The corner posts fill
    those corners completely, so it never shows in the part.
  - The LED holes start at the block face rather than 1 mm outside it, which removes the same
    material.
  - The bore starts at the floor, because `vial_z` is 0 and isn't a variable.
  - The lid cutouts run through the plate only. Where the FeatureScript also cut 1 mm into the LCD
    seal, the seal's ledge opening has already removed that material.
- **API use:**
  - 1 call to create the studio, 77 feature adds (every one OK on the first pass), and 4
    part-naming calls.
  - No FeatureScript-eval calls. Sketch planes, boolean scopes and fillet edges use `queryString`
    queries (`qCreatedBy`, `qNonCapEntity`, `qCapEntity`).
- **Verification (REST, against the old studio):**

  | Part | Volume, both studios (mm³) | Surface area, both (mm²) | Bounding box, new studio |
  |---|---|---|---|
  | Base | 106,857.586 | 78,009.050 | 0–92 × 0–128.5 × 0–51 (old studio gives the same) |
  | Lid | 21,884.265 | 22,609.037 | 0–92 × 0–128.5 × 35.4–44 |
  | Vial cap sleeve | 11,163.969 | 5,951.953 | 27.1–64.9 × 2.7–40.5 × 45.5–65 |

  - Volumes and areas agree to about 1e-11.
  - For the old lid and sleeve, the bounding-box call returned zeros (an API quirk), so the match
    there rests on volume and area.
  - Not yet done for the new studio: STL export and the probe-point check. `render/export_stl.py`
    still exports from the old studio, whose geometry is the same.

---

## 4. V3 parameter reference

The dialog groups below match the feature dialog. "Range" is the limit Onshape enforces. This table
matches `GROUPS` in `cad/build_fs.py` (checked 2026-11-08); if they ever differ, the script is right.

| Group | Parameter | Default | Range | Meaning (dialog label) |
|---|---|---|---|---|
| Print and fit | `wall` | 2 | 0.8 … 10 | Base outer wall |
| Print and fit | `floor_t` | 2 | 0.8 … 10 | Base floor |
| Print and fit | `lid_t` | 2 | 0.8 … 10 | Lid thickness |
| Print and fit | `fit` | 0.3 | 0 … 2 | Clearance per side (lid hole, sleeve skirt, LCD PCB) |
| Print and fit | `corner_r` | 4 | 0 … 20 | Outer corner radius (keep > wall) |
| Lid screws (M3 heat-set inserts) | `post_s` | 9 | 5 … 20 | Corner post size |
| Lid screws (M3 heat-set inserts) | `insert_d` | 4.2 | 2 … 8 | Insert hole diameter (M3 insert OD ~4.8) |
| Lid screws (M3 heat-set inserts) | `insert_depth` | 7 | 2 … 30 | Insert hole depth |
| Lid screws (M3 heat-set inserts) | `screw_d` | 3.4 | 2 … 6 | Lid screw clearance hole |
| Electronics bay | `bb_len` | 84 | 20 … 300 | Breadboard length X (half-size ~83) |
| Electronics bay | `bb_wid` | 55 | 20 … 200 | Breadboard width Y |
| Electronics bay | `bb_gap` | 2 | 0 … 20 | Clearance around the breadboard |
| Electronics bay | `in_h` | 40 | 10 … 150 | Interior height, floor to rim |
| Electronics bay | `part_t` | 1.6 | 0.8 … 10 | Light wall thickness (optics vs bay) |
| Electronics bay | `wire_w` | 24 | 1 … 100 | Wire notch width (top of light wall) |
| Electronics bay | `wire_h` | 10 | 1 … 50 | Wire notch depth |
| Sample vial (SKS 20 mL, measured) | `vial_d` | 27.4 | 5 … 60 | Vial body diameter |
| Sample vial (SKS 20 mL, measured) | `vial_h` | 60 | 20 … 150 | Vial height with cap |
| Sample vial (SKS 20 mL, measured) | `vcap_d` | 24.7 | 5 … 60 | Vial cap diameter |
| Sample vial (SKS 20 mL, measured) | `vcap_h` | 10 | 2 … 40 | Cap height gripped by the sleeve |
| Sample vial (SKS 20 mL, measured) | `vial_fit` | 0.4 | 0 … 3 | Vial-to-bore clearance per side |
| Sample vial (SKS 20 mL, measured) | `vial_z` | 0 | 0 … 30 | Vial bottom above the floor |
| Sample vial (SKS 20 mL, measured) | `front_gap` | 3 | 0 … 30 | Gap between front wall and optics block |
| Sample vial (SKS 20 mL, measured) | `vial_dx` | 0 | -100 … 100 | Vial X offset from centre |
| Optics block and LEDs | `ch_wall` | 2.5 | 0.8 … 10 | Wall at the sensor windows / collar wall |
| Optics block and LEDs | `led_wall` | 9 | 4 … 30 | LED-side wall (LED holes + slit) |
| Optics block and LEDs | `beam_h` | 18 | 5 … 60 | LED column centre above the vial bottom |
| Optics block and LEDs | `led_d` | 4.8 | 1 … 12 | LED hole diameter (body 4.6, lip 5.3) |
| Optics block and LEDs | `led_pitch` | 6 | 2 … 20 | LED vertical spacing |
| Optics block and LEDs | `led_depth` | 5 | 1 … 20 | LED hole depth (LED 5.1 long with lip) |
| Optics block and LEDs | `slit_w` | 2 | 0.5 … 10 | Slit aperture width |
| Optics block and LEDs | `win` | 5 | 1 … 15 | Sensor window size (square) |
| Sensor pockets (slide-in boards) | `pk_s` | 1.5 | 0 … 10 | Gap from block face to board (its parts) |
| Sensor pockets (slide-in boards) | `pk_t` | 2 | 0.8 … 5 | Board slot width |
| Sensor pockets (slide-in boards) | `pk_lip` | 1 | 0.3 … 5 | Rail overlap on each board edge |
| Sensor pockets (slide-in boards) | `pk_back` | 1.2 | 0.6 … 5 | Back rail lip |
| Sensor pockets (slide-in boards) | `pk_side` | 1.5 | 0.6 … 5 | Rail side wall |
| Sensor pockets (slide-in boards) | `pk_cl` | 0.3 | 0 … 2 | Board edge clearance per side |
| Sensor pockets (slide-in boards) | `pk_hz` | 4 | 0 … 20 | Free strip at the board top (header pins) |
| Sensor pockets (slide-in boards) | `tcs_room` | 16 | 0 … 60 | Room behind the 90 deg board (header + plugs) |
| Sensor pockets (slide-in boards) | `tsl_w` | 16 | 5 … 50 | TSL2591 board width |
| Sensor pockets (slide-in boards) | `tsl_h` | 19 | 5 … 50 | TSL2591 board height (header edge up) |
| Sensor pockets (slide-in boards) | `tsl_sz` | 9.5 | 0 … 50 | TSL2591 chip centre above board bottom (measure) |
| Sensor pockets (slide-in boards) | `tsl_su` | 0 | -20 … 20 | TSL2591 chip offset from board centre (+Y) |
| Sensor pockets (slide-in boards) | `tcs_w` | 20.4 | 5 … 50 | TCS34725 board width |
| Sensor pockets (slide-in boards) | `tcs_h` | 20.4 | 5 … 50 | TCS34725 board height (header edge up) |
| Sensor pockets (slide-in boards) | `tcs_sz` | 10.4 | 0 … 50 | TCS34725 chip centre above board bottom |
| Sensor pockets (slide-in boards) | `tcs_su` | 0 | -20 … 20 | TCS34725 chip offset from board centre (+X) |
| Vial cap sleeve | `sl_wall` | 2 | 0.8 … 10 | Skirt wall |
| Vial cap sleeve | `sl_top` | 3 | 0.8 … 20 | Roof above the vial cap |
| Vial cap sleeve | `sl_r` | 1.5 | 0 … 10 | Top edge roundover |
| Vial cap sleeve | `sk_gap` | 1.5 | 0 … 20 | Air gap between skirt and lid (vial seated) |
| Vial cap sleeve | `vcap_fit` | 0.1 | -1 … 2 | Cap pocket = cap diameter + this (press fit) |
| USB-C | `usb_w` | 13 | 2 … 40 | Cutout width |
| USB-C | `usb_h` | 8 | 2 … 30 | Cutout height |
| USB-C | `usb_z` | 14 | 0 … 100 | Cutout centre above the floor |
| LCD (HD44780 1602, measure yours) | `lcd_bw` | 71.3 | 10 … 200 | Bezel width X |
| LCD (HD44780 1602, measure yours) | `lcd_bh` | 26.3 | 5 … 100 | Bezel height Y |
| LCD (HD44780 1602, measure yours) | `lcd_fit` | 0.25 | 0 … 3 | Window clearance per side |
| LCD (HD44780 1602, measure yours) | `lcd_bz_t` | 7 | 2 … 20 | Bezel top above PCB top (keep > lid) |
| LCD (HD44780 1602, measure yours) | `lcd_pcb_w` | 80 | 10 … 200 | PCB width X |
| LCD (HD44780 1602, measure yours) | `lcd_pcb_h` | 36 | 5 … 100 | PCB height Y |
| LCD (HD44780 1602, measure yours) | `lcd_pcb_t` | 1.6 | 0.5 … 5 | PCB thickness |
| LCD (HD44780 1602, measure yours) | `lcd_dx` | 75 | 5 … 200 | Mounting hole spacing X |
| LCD (HD44780 1602, measure yours) | `lcd_dy` | 31 | 5 … 100 | Mounting hole spacing Y |
| LCD (HD44780 1602, measure yours) | `lcd_hole` | 2.8 | 1 … 6 | Mounting screw hole (M2.5) |
| LCD (HD44780 1602, measure yours) | `seal_t` | 1.6 | 0.8 … 5 | Light-seal skirt wall |
| LCD (HD44780 1602, measure yours) | `seal_lip` | 1 | 0.3 … 5 | Ledge under the PCB edge |
| LCD (HD44780 1602, measure yours) | `lcd_off` | 0 | -100 … 100 | LCD Y offset from the breadboard centre |

**Derived values** are computed inside the feature and can't be edited directly. Defaults in
brackets:

- **Box:**
  - `box_l` = bb_len + 2·bb_gap + 2·wall (92)
  - `box_w` = optics_d + part_t + bb_wid + bb_gap + post_s + 2·wall (128.5)
  - `base_h` = floor_t + in_h (42)
  - `post_c` = wall + post_s/2 (6.5): insert and lid-screw centres, measured from the outer edges
- **Optics zone:**
  - `optics_d` = front_gap + bore + 2·ch_wall + pk_depth + tcs_room (56.9)
  - `pk_depth` = pk_s + pk_t + pk_back (4.7): how far each sensor pocket stands off the block face
  - `bb_cy` = wall + optics_d + part_t + bb_wid/2 (88). The USB-C cutout centres on it, and so does
    the LCD (at `bb_cy` + `lcd_off`).
- **Vial:**
  - `bore` = vial_d + 2·vial_fit (28.2)
  - `vial_cx` = box_l/2 + vial_dx (46); `vial_cy` = wall + front_gap + ch_wall + bore/2 (21.6)
- **Optics block:** x from vial_cx − bore/2 − led_wall (22.9, the LED face) to vial_cx + bore/2 +
  ch_wall (62.6, the 180° face). y from vial_cy − bore/2 − ch_wall (5.0) to vial_cy + bore/2 +
  ch_wall (38.2, the 90° face). It runs from the floor top to the rim.
- **Beam and LEDs:**
  - `beam_z` = floor_t + vial_z + beam_h (20)
  - LED centres = beam_z + (−1.5, −0.5, +0.5, +1.5)·led_pitch (11, 17, 23, 29)
  - Slit height = 3·led_pitch + led_d (22.8), centred on beam_z
- **Collar and sleeve:**
  - `collar_d` = bore + 2·ch_wall (33.2)
  - `collar_top` = vial bottom + vial_h − vcap_h − 1 (51)
  - `sk_z` = base_h + lid_t + sk_gap (45.5); sleeve top = vial bottom + vial_h + sl_top (65)
  - `sl_d` = collar_d + 2·(fit + sl_wall) (37.8)
- **Sensor pockets:**
  - Board bottoms: `beam_z − tsl_sz` (10.5) and `beam_z − tcs_sz` (9.6). The rails stop `pk_hz`
    below the board tops (z 25.5 and 26.0).
  - Pocket block widths: tsl_w + 2·(pk_cl + pk_side) (19.6) and tcs_w + 2·(pk_cl + pk_side) (24.0).
  - Board centres: vial_cy − tsl_su and vial_cx − tcs_su, so the chip lands on the beam.
- **LCD:**
  - `lcd_drop` = lcd_bz_t − lid_t (5): the PCB top sits this far below the lid underside, which puts
    the bezel top flush with the lid top.
  - Seal outer = PCB + 2·(fit + seal_t) (83.8 × 39.8); PCB pocket = PCB + 2·fit (80.6 × 36.6);
    ledge opening = PCB − 2·seal_lip (78 × 34).

**Built-in checks:** the feature stops with a red error if:
- `lcd_bz_t` ≤ `lid_t`;
- the vial is too short for the collar to reach above the lid;
- a sensor board would sit below the floor.

---

## 5. Hardware components

### 5.0 Parts list (V3)

| Item | Qty | Notes | See |
|---|---|---|---|
| ESP32-WROOM-32D DevKit | 1 | connector type and CC resistors to confirm | §5.1, §5.2 |
| Half-size breadboard | 1 | about 84 × 55 | §5.11 |
| Through-hole LEDs: red, green, yellow, IR | 4 | body ⌀4.6, lip ⌀5.3 (measured) | §5.3 |
| LED series resistors | 4 | values not chosen yet | §5.3 |
| TSL2591 breakout (EC Buying) | 1 | 180° pocket | §5.4 |
| TCS34725 breakout (Adafruit #1334) | 1 | 90° pocket; LED pin to GND | §5.5 |
| TCA9548A I2C multiplexer | 0–1 | only if the sensors don't get separate I2C buses | §5.6 |
| HiLetgo HD44780 1602 LCD, blue backlight, 5 V | 1 | | §5.7 |
| 10 kΩ potentiometer | 1 | LCD contrast (V0) | §5.7 |
| 74AHCT125 (or 74HCT245) 5 V buffer | 0–1 | only if 3.3 V logic doesn't drive the LCD reliably | §5.7 |
| SKS 20 mL PET vial with cap | 2 or more | one for the water blank, plus one per sample | §5.8, §6 |
| M3 heat-set inserts | 4 | base corner posts | §5.10 |
| M3 × 6 screws | 4 | lid | §5.10 |
| M2.5 × 12 screws + M2.5 nuts | 4 + 4 | LCD | §5.10 |
| Printed parts: base, lid, vial cap sleeve | 3 | dark PLA or PETG | §5.12, §7 |
| USB-C cable to the iPhone | 1 | C-to-C needs CC resistors on the board; otherwise use C-to-micro-B | §5.2 |
| 5.1 kΩ resistors | 0–2 | only for a USB-C board without CC resistors | §5.2 |
| Jumper wires; black heat-shrink or tape | — | wiring; LED backs if light leaks | §5.3 |

### 5.1 Microcontroller: ESP32-WROOM-32D DevKit (on a half-size breadboard)

- **Chip:** ESP32 dual-core Xtensa LX6, up to 240 MHz, 520 KB SRAM, Wi-Fi 802.11 b/g/n, Bluetooth 4.2
  (Classic + BLE). The WROOM-32D module typically has 4 MB flash. Logic is 3.3 V.
- **DevKit:** USB-UART bridge (CP2102 or CH340, check yours), 3.3 V LDO, and a 5 V/VIN pin that carries
  USB 5 V.
- **Connector:** not confirmed. The brief describes the board's USB-C port as exposed through the
  case, so it's probably a USB-C board: check it, and check its CC resistors (§5.2). The case cutout
  is 13 × 8, which should fit most USB-C and micro-USB cable plugs. Check yours: the plug has to reach
  through the 2 mm wall to the port.
- **Pin constraints when you wire it:**
  - GPIO 6–11 are used by the flash: never use them.
  - GPIO 34–39 are input-only.
  - Strapping pins 0, 2, 5, 12 and 15 affect boot: avoid them for outputs that are pulled at reset.
  - ADC2 can't be used while Wi-Fi is on.
- **Two hardware I2C controllers.** This matters because both sensors use the same address (§5.6).
- **Pin map:** not decided yet. Record it here once the board is wired.

### 5.2 Power and link from the iPhone (USB-C)

- iPhones with USB-C (15 and later) can power accessories over USB-C at 5 V. Apple quotes up to
  4.5 W. Expected draw is roughly 100–250 mA for the ESP32 (more with radio bursts), plus the LCD
  backlight and one LED at a time, which is well within budget.
- **CC-resistor caveat:** a USB-C source only turns VBUS on when the device pulls each CC pin to
  ground through 5.1 kΩ (Rd).
  - Many cheap USB-C ESP32 boards leave out these resistors. A C-to-C cable from the iPhone then
    delivers **no power**. Test this early.
  - Fixes: add 5.1 kΩ from CC1 and CC2 to GND, or use a micro-USB board with a USB-C→micro-B cable
    (those cables include Rd).
- **Data link:** iOS apps can't open generic USB serial devices (CP2102/CH340) without Apple MFi
  accessory support, and iOS Safari has no Web Serial. So use USB-C for **power** and **BLE** (built
  into the ESP32) for **data**. This informs the open "USB-C serial vs BLE" decision.
- **App stack:** iOS Safari has no Web Bluetooth either, so a plain web app can't talk to the device.
  BLE needs a native app: Swift, or React Native/Expo with a development build. This bears on the open
  app-stack decision in CLAUDE.md.

### 5.3 LEDs (4 pieces: red, green, yellow, IR)

- **What the team has:** four small through-hole LEDs: red, green and yellow, plus an IR emitter.
- **Measured** (2026-11-07):
  - body ⌀4.6, lip/flange ⌀5.3;
  - length 0.2 in = 5.08 including the lip. This was measured before the diameter correction (the
    first measurement said 0.12 in = 3.05 body / 0.15 in = 3.81 lip), so **re-measure the length**.
- **Which LED type?** A standard 5 mm round LED has a ⌀5.0 body, a ⌀5.8 flange and stands about 8.6
  tall. These are thinner and much shorter, closer to a 4.8 mm "straw hat" LED. Straw-hat LEDs have
  a wide beam (often 100–120°), so less of their light gets through the slit. That's an inference
  from the sizes; check the actual part.
- **In V3:**
  - holes ⌀4.8 (FDM prints holes about 0.1–0.2 undersized, giving a snug push fit), 5 deep;
  - the lip stops the LED at the optics block's −X face;
  - pitch 6 (lips have 0.7 between them);
  - if the LEDs are longer than 5 mm below the lip, raise `led_depth` (and `led_wall`) so they seat
    fully.
- **Hole order:** record which LED goes in which hole (z = 11, 17, 23, 29). The two middle holes
  (17, 23) line up best with the 5 × 5 sensor windows at z = 20, so put the most important
  wavelengths there.
- **Wavelengths and part numbers:** not recorded yet. Typical values are red 620–630 nm, yellow about
  590 nm, green about 525 nm (InGaN) or about 570 nm (GaP), and IR 850 or 940 nm. Record the actual
  parts.
- **Drive:**
  - one LED at a time, each through its own series resistor, R ≈ (3.3 V − Vf) / I.
  - Typical Vf: red/yellow 1.8–2.2 V, GaP green about 2.1 V, InGaN green 2.8–3.4 V (too close to
    3.3 V: drive it from 5 V through a transistor), IR 1.2–1.5 V.
  - Keep each GPIO at 20 mA or less, or switch the LEDs with transistors.
  - LED output drifts with temperature, so warm up briefly and take a blank every session (§6).
- **Light leak:** LED epoxy also leaks light backwards into the case. Dark readings (all LEDs off)
  can't show this. To test it, put an opaque-filled vial in the bore and light each LED in turn:
  anything above the dark reading is light getting around the vial. If so, cover the LED backs with
  black heat-shrink or tape.

### 5.4 TSL2591 high-dynamic-range light sensor: EC Buying breakout (180°, transmission)

- **Listing:** "TSL2591 High Dynamic Light Sensor Breakout Module 3V 5V I2C High Range Optical Sensor
  Development Tool" by EC Buying (Amazon). A PDF of the listing is saved on the machine used for the
  CAD: `C:\Users\trevo\Downloads\EC Buying TSL2591 High Dynamic Light Sensor Breakout Module 3V 5V I2C
  High Range Optical Sensor Development Tool_ Amazon.com_ Industrial & Scientific.pdf`.
- **Chip:** ams/OSRAM TSL25911.
  - I2C address **0x29** (fixed). Adafruit's #1980 page says the chip also answers on 0x28 (its learn
    guide says 0x29 only), so an I2C scan may show both.
  - Two 16-bit channels: CH0 full spectrum (visible + IR) and CH1 IR.
  - About 188 µlux to 88,000 lux (600M:1).
  - Gain 1× / 25× / 428× / 9876×; integration time 100–600 ms.
- It sees all four LEDs including **IR**, which is why it sits at **180°** (straight through).
- **Board** (from the listing):
  - About 19 × 16 × 1. It has a regulator and runs on 3.3–5 V. If the board really is 1 mm thick,
    the 2.0 mm slot (`pk_t`, shared with the TCS34725 pocket) leaves about 1 mm of play.
  - Installed with the header edge up and the 19 mm side vertical.
  - Pins, left to right on the silkscreen in the listing photo: VIN, GND, 3Vo, INT, SDA, SCL. The
    listing text names only Vin, GND, SCL, SDA and INT.
- **Pin order:** Adafruit's current TSL2591 board (#1980, STEMMA QT version; from its fab print)
  orders its pins VIN, 3Vo, GND, SCL, SDA, INT, so Adafruit wiring diagrams don't carry over
  pin-for-pin. Wire from the silkscreen, and confirm the address with an I2C scan.
- **Chip position on the board is NOT verified.** The default `tsl_sz` = 9.5 (centre of the 19 mm
  height) and `tsl_su` = 0 assume a centred chip. **Measure** from the board's bottom edge to the
  chip centre and set `tsl_sz` / `tsl_su` so the chip lands on the beam.

### 5.5 TCS34725 RGB colour sensor: Adafruit #1334 (90°, side scatter)

- **Listing:** "RGB Color Sensor with IR filter and White LED - TCS34725" (Adafruit product 1334).
  The original brief named the CJMCU-34725, a different TCS34725 board whose outline and chip
  position may differ. If that board is used instead, measure it and set `tcs_w`, `tcs_h`, `tcs_sz`
  and `tcs_su`.
- **Chip:** ams TCS34725.
  - I2C address **0x29** (fixed).
  - Red, green, blue and clear channels, 16-bit each, with an **IR-blocking filter**.
  - Gain 1× / 4× / 16× / 60×; integration time 2.4–614 ms; dynamic range 3.8M:1.
- Because it can't see the IR LED, it sits at **90°**, where it measures colour scatter (turbidity).
- **Board** (Adafruit fab print): 20.3 × 20.3 (0.8 in).
  - Adafruit's product page lists 20.44 × 20.28 and 3.23 g. The pocket slot takes boards up to 21.0
    (`tcs_w` 20.4 + 2 × `pk_cl` 0.3).
  - In the fab print (header along the bottom edge), the sensor centre is 10.4 (0.41 in) from the
    top and left edges, so it's about centred. Installed header-up, the chip is therefore 10.4 above
    the board's bottom edge, which is `tcs_sz`.
  - A white LED (about 4150 K, with a MOSFET driver) sits 3.3 to the left of the sensor. Boards made
    since 2020-09-25 use a Würth 158302250 LED.
  - The SMD parts are on the sensor side, hence the 1.5 mm `pk_s` clearance. No part heights are
    recorded, so check that the tallest one clears it (§8).
  - Header: LED, INT, SDA, SCL, 3V3, GND, VIN.
- **Tie the LED pin to GND**, or its white LED shines straight into the window and swamps the
  measurement. Adafruit also allows driving it from a GPIO, or wiring it to INT.
- **Availability:** Adafruit lists #1334 as no longer stocked, and points to the APDS9960 (#3595),
  which is a different sensor. Get a spare, or plan to refit the 90° pocket for whatever board
  replaces it.
- In V3 the board is held by `tcs_w`/`tcs_h` 20.4 (+0.3 per side), with the chip at `tcs_sz` = 10.4
  above the bottom edge.

### 5.6 I2C address conflict: both sensors are 0x29

The TCS34725 and TSL2591 both have the fixed address 0x29, so they **can't share one I2C bus**. Two
fixes:
- Use the ESP32's two I2C controllers, `Wire` and `Wire1`, one sensor each, on separate SDA/SCL pin
  pairs.
- Add a TCA9548A I2C multiplexer.

### 5.7 Display: HiLetgo HD44780 1602 LCD (16×2, blue backlight, 5 V, parallel)

- **Listing:** "HiLetgo 2pcs HD44780 1602 LCD Display Module DC 5V 16x2 Character LCM Blue
  Blacklight". The device uses one of the pair.
- **Pins:** 1 VSS, 2 VDD (5 V), 3 V0 (contrast, wiper of a 10 kΩ pot), 4 RS, 5 RW, 6 E, 7–14 D0–D7,
  15 A (backlight +), 16 K (backlight −).
- **Wiring:** 4-bit mode uses 6 GPIOs (RS, E, D4–D7). Tie RW to GND (write-only), so the LCD never
  drives 5 V onto the ESP32's pins.
- **3.3 V logic:** it usually works with these 5 V modules, but it's out of spec on paper: the
  TC1602A-09T sheet asks for VIH ≥ 0.7·VDD (3.5 V at 5 V). Test early. If the display misbehaves, add
  a 5 V buffer such as a 74AHCT125 or 74HCT245.
- **Backlight:** the two datasheets disagree.
  - TC1602A-09T (Adafruit #181, white LED backlight): about 3.2 V at 30 mA. It warns never to put 5 V
    straight across pins 15/16.
  - GDM1602K: 4.2 V typical at 120 mA (160 mA max).
  - Many of these modules already have a series resistor on pin 15. Look for one (or measure the
    current) before wiring pin 15 to 5 V.
- **Mechanical defaults** (standard GDM1602K drawing; **measure your module**):

  | Item | Value | Parameter |
  |---|---|---|
  | PCB | 80 × 36 × 1.6 | `lcd_pcb_*` |
  | Mounting holes | ⌀2.5 at 75 × 31 spacing | `lcd_dx` / `lcd_dy` |
  | Metal bezel | 71.3 × 26.3 | `lcd_bw` / `lcd_bh` |
  | Bezel top above PCB top | about 7 | `lcd_bz_t` |

- **Other sources differ slightly.**
  - Adafruit's standard 16×2 LCD (#181) lists its PCB as 80.6 × 36 × 1.0, and 8.4 for "height
    (PCB + screen)". SparkFun lists about 3.15 × 1.425 in (80.0 × 36.2).
  - The web pages checked on 2026-11-07 didn't state the hole spacing; 75 × 31 comes only from the
    GDM1602K drawing.
  - An 80.6 mm PCB would have **zero clearance** in the default pocket (80 + 2 × 0.3 = 80.6), so
    measure yours and set `lcd_pcb_w`.
- **Mounting:** M2.5 × 12 screws from the lid top through the lid (2), the 5 mm gap and the PCB
  (1.6), with an M2.5 nut underneath. Tighten until the PCB edge seats against the ledge. The bezel
  then sits flush in the window.

### 5.8 Sample vial: SKS Science 20 mL (replaces the cuvette from V3)

- **Product:** SKS Science "Plastic Lab Vials, Clear PET Sample Lab Vials w/ White Polypropylene
  PE-F217 Lined Caps", https://www.sks-science.com/plastic-laboratory-vials-p-5588.html.
  - 20 mL clear PET with a 22/400 neck, and a white ribbed PP screw cap with a PE-F217 liner.
  - Stock numbers: 0043-98SP (12 per bag), 0043-98 (144 per bag), 0043-98B (1008 per case). Prices
    on 2026-11-07: $18.48, $123.84 and $725.76.
  - The page says the vials ship with the caps not attached.
  - On 2026-11-07 it also showed a "currently unavailable / Notify Me When Available" block without
    saying which item it meant, so stock was unclear.
  - It gives no outside diameter, height, wall thickness or drawing.
- **Measured** by the team with calipers (2026-11-07): body OD **27.4**, cap OD **24.7**, total height
  **60** with the cap on. The first estimate was "about 1 in" (25.4) across.
- **Not yet measured:**
  - wall thickness and inside diameter, which set the fill line, §6;
  - bottom shape (flat or pushed-up);
  - real cap height: `vcap_h` = 10 must not exceed it;
  - neck/shoulder geometry.
- **Light:**
  - Clear PET passes visible light and near-IR, so the walls aren't a problem for the 850/940 nm IR
    LED.
  - Keep vials clean and unscratched; scratches scatter light.
  - The white PP cap lets some light through, which is one reason the dark sleeve covers it.

### 5.9 Cuvette (V1/V2 only, superseded)

Standard 12.5 × 12.5 × 45 cuvette with a 10 mm path. Variables `cuv_w`, `cuv_h`, `cuv_fit` = 0.35 and
`cuv_grab` = 10 in V1/V2.

### 5.10 Fasteners

| Item | Qty | Where | Spec |
|---|---|---|---|
| M3 heat-set insert | 4 | base corner posts | measured OD 0.19 in (4.83), length 0.15 in (3.81); hole ⌀4.2 × 7 deep (`insert_d`, `insert_depth`) |
| M3 × 6 screw (button or socket head) | 4 | lid to base | lid clearance ⌀3.4 (`screw_d`) |
| M2.5 × 12 screw + M2.5 nut | 4 + 4 | LCD to lid | lid holes ⌀2.8 (`lcd_hole`) |

- The team asked for a standard hole size for their inserts, slightly under the measured OD. The
  ⌀4.2 hole is that standard size for M3 inserts of about ⌀4.8.
- The hole is 7 deep, so the screw tip has room below the 3.8 mm insert. An M3 × 6 screw through the
  2 mm lid engages about 4 mm.
- Set the inserts with a soldering iron at about 220–240 °C for PLA. Press them straight down until
  flush.

### 5.11 Breadboard

Half-size, about 82–84 × 54–55 (`bb_len` 84 × `bb_wid` 55; measure). It sits in the back bay, centred
at (46, 88). The ESP32's USB port should line up with the left-wall cutout; set `usb_z` after
measuring the port height above the floor with the DevKit plugged in.

### 5.12 Filament

Use black or very dark PLA or PETG for **all three parts**. Light-coloured PLA passes enough ambient
light to ruin the readings. The outer walls are 2 mm (5 lines with a 0.4 nozzle). Inside, the light
wall and the LCD seal skirt are 1.6 (4 lines), and the sensor-pocket rails 1.2–1.5.

---

## 6. Optics design notes

- **Why a vertical LED column (V3):**
  - A beam that crosses a round vial at lateral offset *d* from its axis travels a chord
    2√(r² − d²) through the liquid.
  - With inner radius r ≈ 12.7 (assuming a 1 mm wall), a 2 × 2 grid like V2's (d = 3.25) gives
    24.55 mm, 3.3 % shorter than on-axis (25.4).
  - Off-axis beams also hit the curved wall at an angle and get bent sideways, partly missing the
    sensor.
  - On the axis plane, incidence is normal and the chord is the full diameter. Light entering
    through the 2 mm slit (d ≤ 1) sees a chord at most about 0.3 % shorter (0.31 % at d = 1). The
    light that reaches the 180° chip, which is also on the axis plane, crosses the full diameter.
- **Vertical spread:**
  - The LED tips (x ≈ 26.9) are about 36.6 from the 180° chip (x ≈ 63.5).
  - The straight line from an outer LED (±9 from the sensor height) to the chip is 13.8° off
    horizontal. The ray that actually reaches the chip bends at the vial walls: about 17.2° in air
    and 12.8° in water, so its path through the water is about 2.5 % longer than a level beam's.
  - The inner LEDs (±3): about 5.8° in air, 4.4° in water, +0.3 %.
  - Both assume a 1 mm PET wall (n ≈ 1.57) and water (n = 1.333). These factors are constant per LED,
    so they cancel when each LED is normalised to its own blank.
- **Lensing:** in the horizontal plane, the water-filled vial acts as a cylindrical lens (focal line
  about 27 from the axis for parallel light). It concentrates light toward the 180° chip, which is
  about 17.5 from the axis.
- **Fill line:**
  - The liquid must cover the whole slit: its top is at z = 31.4, i.e. 29.4 above the vial's outside
    bottom.
  - Mark a fill line at about **33 mm** above the bottom.
  - Assuming a 1 mm wall and a flat 1 mm bottom (inner ⌀25.4, about 0.51 mL per mm of height), the
    33 mm line holds about **16 mL**. Just covering the slit (29.4) takes about 14.4 mL, and the top
    LED's centre (27) about 13 mL. Confirm once the inside diameter and bottom are measured.
  - Lowering `beam_h` reduces the sample needed, but keep the bottom LED clear of settled filler.
- **Suggested measurement routine** (for the firmware/app team):
  1. Sleeve on and lid closed.
  2. **Dark** reading with all LEDs off. Subtract it from everything.
  3. **Blank:** the same vial type filled with clean water. Record I₀ per LED.
  4. **Sample:** record I per LED, one LED at a time, with a short settle time.
  5. Absorbance per LED: A = log₁₀(I₀ / I) from the TSL2591 (CH0; use CH1 for IR).
  6. Scatter index: TCS34725 clear/RGB counts at 90° relative to the blank.
  7. Use the same gain and integration settings for blank and sample.

---

## 7. Printing and assembly (V3)

**Files:**
- Export STLs from Onshape: right-click each part → Export → STL, in mm.
- Or run `onshape-mcp/.venv/Scripts/python.exe cad/render/export_stl.py [versionId]`. It writes
  `cad/render/stl/{base,lid,sleeve}.stl` (binary, mm, fine tessellation) from a saved version, V3 by
  default.
- Either way, after changing parameters, save a new version first, then export from it.

**Print orientation** (no supports needed for any part):

| Part | Orientation | Why |
|---|---|---|
| Base | floor down | Largest bridges: USB-C 13 mm, windows 5 mm, LED holes ⌀4.8, slit 2 mm |
| Lid | **upside down** (top face on the bed) | The LCD ledge and skirt then grow upward and the top face prints smooth |
| Vial cap sleeve | **upside down** (roof on the bed) | The cap pocket and skirt open upward; the inner step at the skirt is not an overhang |

**Print the sleeve first.** It's small (11 cm³) and lets you tune the press fit on the real cap
(`vcap_fit`) before the long base print.

**Fits to tune after a test print:**
- `vial_fit` 0.4: the vial should drop in and lift out freely.
- `vcap_fit` 0.1: the sleeve should stay on the cap when lifting the vial.
- `led_d` 4.8: the LED should push in snugly.
- `pk_cl`, `pk_t`: the boards should slide in without play.
- `fit` 0.3: lid hole and sleeve skirt around the collar.

**Assembly:**
1. Heat-set the 4 M3 inserts into the base's corner posts.
2. Push the 4 LEDs into the −X face of the optics block until the lips seat. Bend the leads toward
   the breadboard and record which colour is at which height.
3. Slide the **TSL2591** into the +X (180°) pocket: chip toward the vial, header edge up. Slide the
   **TCS34725** into the +Y (90°) pocket: chip toward the vial, header edge up, LED pin tied to GND.
4. Put the breadboard and ESP32 in the back bay, USB port at the left-wall cutout. Route the wires
   through the light-wall notch.
5. Screw the LCD up against the lid's ledge (4 × M2.5 × 12 + nuts), bezel through the window.
6. Close the lid onto the collar and screw it down (4 × M3 × 6).
7. **Use:**
   - Fill the vial to the line and screw on its cap.
   - Press the sleeve onto the cap.
   - Lower the vial into the bore until it rests on the bottom. The skirt covers the collar.
   - Lift by the sleeve to remove it.

---

## 8. Open items and things to measure

- [ ] LED length below the lip (`led_depth`), wavelengths and part numbers, LED type (§5.3), and the
  hole-to-colour map.
- [ ] TSL2591 board: outline (the listing says 19 × 16 × 1), thickness (sets `pk_t`), chip position
  (`tsl_sz`, `tsl_su`), which side the parts are on, pin order and I2C address (§5.4).
- [ ] TCS34725 board: confirm 20.3 × 20.3, the chip at 10.4 from the edge opposite the header, the
  board thickness, and that the tallest part on the sensor side clears `pk_s` = 1.5 (§5.5). Adafruit
  no longer stocks it, so get a spare.
- [ ] Sleeve: decide whether it needs the knob that the chosen design described (§3 V3).
- [ ] Vial: wall thickness / inside diameter (fill line), bottom shape, real cap height (`vcap_h`).
- [ ] LCD: bezel W/H, bezel height above the PCB (`lcd_bz_t`), PCB size (an 80.6 PCB needs
  `lcd_pcb_w` raised, §5.7), hole spacing.
- [ ] ESP32 DevKit: connector type, USB port height (`usb_z`), whether its USB-C has CC resistors
  (§5.2).
- [ ] Breadboard size; `in_h` clearance between the LCD's header wires and the ESP32.
- [ ] Firmware: split I2C buses (§5.6); pin map (§5.1); LED resistor values (§5.3); dark/blank/sample
  routine (§6).
- [ ] Delete the "zz_api_probe (temporary)" tab in Onshape by hand.
- [ ] After the first print, record the tuned fit values here as V3.1 or V4.
- [ ] Presentation drawings: write `cad/render/drawings.py` and produce the sheets in `schematics/`
  (§9).

**Ideas for later (not adopted):** a multi-channel spectral sensor such as the AS7341 would give a
finer optical fingerprint than four LEDs. Claude suggested it on 2026-11-07, just before the team's
brief fixed the four-LED, two-sensor design.

---

## 9. Presentation graphics

**Goal (2026-11-08):** slide images of the CAD for the team's presentation, in a few styles. They
should be simple, but show off the design. The team then specified CAD sketches or blueprint-style
drawings rather than photoreal renders. Everything is drawn from the real V3 geometry. The files are
in `cad/render/`.

| Step | File | Command | Output |
|---|---|---|---|
| 1. Export the printed parts | `export_stl.py` | `onshape-mcp/.venv/Scripts/python.exe cad/render/export_stl.py [versionId]` | `stl/base.stl` (7,430 triangles), `stl/lid.stl` (6,630), `stl/sleeve.stl` (17,800). Binary, mm, angle tolerance 0.04 rad, chord 0.005 mm; V3 by default. About 4 API calls, none on the eval quota |
| 2. Textures | `textures.py` | `python cad/render/textures.py` | `tex/lcd_{hero,exploded,cutaway}.png` (HD44780 5×8 dot-matrix text on a blue backlight) and `tex/breadboard.png` |
| 3. Scene and mesh dump | `scene.py` (Blender 5.1.1) | `blender -b --factory-startup -P cad/render/scene.py -- --dump assembled` (or `exploded`, `cut_y`, `cut_z`) | `out/mesh_<stage>.npz`: world-space triangles in mm, with object names and groups |
| 4. Line drawings | `lineart.py` (numpy) | imported by the sheet script | hidden-line views, section loops, SVG paths |
| Shelved: Cycles renders | `scene.py -- --shot hero` (or `exploded`, `cutaway`); `render_all.sh` | | `out/<shot>.png` and `.json` label anchors |

Blender is at `C:/Program Files/Blender Foundation/Blender 5.1/blender.exe`.

**What the scene contains:**
- The three printed parts are the real meshes.
- Everything else is modelled in `scene.py` from §5 and placed where `build_fs.py` puts its holes
  and pockets at default parameters:
  - the vial (1 mm wall assumed, liquid to the 33 mm fill line, ribbed cap);
  - the four LEDs with legs;
  - both sensor boards with chips and headers;
  - the LCD (PCB, bezel, screen) with its screws and nuts;
  - the inserts and lid screws;
  - the breadboard with an ESP32 DevKit (USB-C port at the left-wall cutout);
  - a USB-C plug and cable.
- These are visual stand-ins, not measurements.
- The LED colours in the renders follow the team's wiring diagram (white, red, green, blue; since
  2026-11-08), placed blue at z 11, green 17, red 23, white 29. That order is for illustration only;
  the real order isn't decided (§5.3).

**Mesh dumps (2026-11-08):**

| Stage | Objects | Triangles | Contents |
|---|---|---|---|
| `assembled` | 132 | 54,124 | everything in place except the USB-C plug and cable |
| `exploded` | 134 | 54,148 | parts moved apart: +Z by lid 46, lid screws 66, vial 104, sleeve 124, TSL2591 board 30, TCS34725 board 42; USB-C plug −22 in X |
| `cut_y` | 119 | 35,940 | section A–A: everything at y < 21.62 removed (a plane 0.02 off the vial axis) |
| `cut_z` | 72 | 12,536 | section B–B: everything above z = 18.5 removed (through the z = 17 LED hole and both windows) |

- Only `exploded` keeps the USB-C plug, and no dump has its cable: `scene.py` removes them before
  dumping.
- The cuts are exact Blender booleans.
- Printed parts get a separate material on their cut faces.
- LEDs are only removed if they're entirely on the cut-away side.

**lineart.py:**
- Orthographic views: top, front, left, right, and two isometrics (`iso` from front-left-top,
  `iso_r` from front-right-top). Screen units are px at a chosen px/mm scale.
- A scanline z-buffer and face-id buffer.
- Edges are silhouettes, creases (over 22° by default) and open boundaries. Each edge is tested
  against a 3 × 3 max-filtered z-buffer (0.02 mm tolerance) to split visible from hidden, then
  chained into polylines and simplified.
- `section()` slices a mesh with an axis plane into closed loops for hatching.
- Speed: about 2 s per view at 5 px/mm. The first version took about 120 s per view, because long
  sliver triangles in the STL's flat faces have huge bounding boxes.

**Status (2026-11-08):**
- The photoreal Cycles renders were first dropped at the team's request, then brought back for the
  repo documentation. On 2026-11-08 the three shots in `out/` (hero, exploded, cutaway, with their
  `.json` files) were re-rendered at 2560 × 1440, 128 samples, as 8-bit PNGs, with `RENDER_CPU=1 bash
  cad/render/render_all.sh 2560x1440 128`. On this laptop's Intel Arc 140V the oneAPI GPU path failed
  with "device lost" on hero and exploded, so `RENDER_CPU=1` forces the CPU. `scene.py`'s docstring
  mentions a `compose.py` that was never written.
- `lineart.py` drew a six-view test sheet (top, front, left, A–A, B–B, iso). Some outlines on curved
  surfaces were missing; the silhouette rule was fixed afterwards but hasn't been re-tested.
- Not done yet: the sheet script `cad/render/drawings.py` and the output folder `schematics/` (a
  3840 × 2160 PNG plus an SVG per sheet). Planned styles:
  1. a blueprint sheet with orthographic views, dimensions and a title block;
  2. a dark optics cross-section showing the four beams;
  3. an exploded isometric line drawing with labels;
  4. a notebook-style pencil sketch with handwritten notes.

**Tool notes:**
- Blender 5.1:
  - Principled BSDF inputs have names like "Transmission Weight";
  - `Mesh.set_sharp_from_angle()` replaces auto-smooth;
  - import mm STLs with `bpy.ops.wm.stl_import(global_scale=0.001)`;
  - call `bpy.context.view_layer.update()` before reading `matrix_world` after moving objects.
- SVG to PNG with headless Chrome:
  `chrome.exe --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1
  --window-size=W,H --screenshot=<png> <file:///…svg>`.
- Fonts on this machine: Bahnschrift, Consolas, Segoe UI, Ink Free, Segoe Print and Segoe Script.

---

## Appendix A. V1 and V2 variable tables

These were read from the saved Onshape versions. The expressions and descriptions below are exactly
what was stored in each version. Some notes were corrected later. For example, the `led_d` note
"real LEDs are 3 mm" was wrong: the LEDs measure 4.6 body / 5.3 lip (§5.3). "—" means the variable
didn't exist in that version.

| Variable | V1 | V2 | Description (V2 wording; V1 where V2 lacks it) |
|---|---|---|---|
| `wall` | `2 mm` | `2 mm` | Base outer wall thickness |
| `floor_t` | `2 mm` | `2 mm` | Base floor thickness |
| `lid_t` | `2 mm` | `2 mm` | Lid thickness |
| `fit` | `0.3 mm` | `0.3 mm` | Clearance per side: lid hole + cap around the chamber, LCD PCB in its skirt |
| `corner_r` | `4 mm` | `4 mm` | Outer corner radius of base and lid (must be > wall) |
| `post_s` | — | `9 mm` | Corner post size (square); each holds one M3 heat-set insert |
| `insert_d` | — | `4.2 mm` | Heat-set insert hole diameter (M3 insert, OD ~4.8 mm measured) |
| `insert_depth` | — | `7 mm` | Insert hole depth (insert is 3.8 mm long + room for the screw tip) |
| `screw_d` | — | `3.4 mm` | Lid clearance hole for the M3 screws |
| `bb_len` | `84 mm` | `84 mm` | Breadboard length (X). Half-size ~83, full-size ~165 |
| `bb_wid` | `55 mm` | `55 mm` | Breadboard width (Y) |
| `bb_gap` | `2 mm` | `2 mm` | Clearance around the breadboard |
| `optics_d` | `32 mm` | `32 mm` | Depth (Y) of the optics zone in front of the light wall |
| `in_h` | `40 mm` | `40 mm` | Interior height, floor to rim (fits ESP32 on breadboard + LCD under lid) |
| `part_t` | — | `1.6 mm` | Light wall thickness (between the optics zone and the USB-C/electronics bay) |
| `wire_w` | — | `24 mm` | Wire notch width at the top of the light wall |
| `wire_h` | — | `10 mm` | Wire notch depth down from the rim |
| `cuv_w` | `12.5 mm` | `12.5 mm` | Cuvette outer width (standard 12.5 x 12.5) |
| `cuv_h` | `45 mm` | `45 mm` | Cuvette height |
| `cuv_fit` | `0.35 mm` | `0.35 mm` | Cuvette clearance per side |
| `cuv_grab` | `10 mm` | `10 mm` | How far the cuvette sticks up out of the chamber (to grab it) |
| `beam_h` | `15 mm` | `15 mm` | Light beam height above the cuvette bottom |
| `ch_wall` | `2.5 mm` | `2.5 mm` | Chamber wall thickness on the sensor sides |
| `led_wall` | `9 mm` | `9 mm` | LED-side wall thickness |
| `collar` | `4 mm` | `4 mm` | Chamber height above the lid (the cap slides over it) |
| `led_d` | `5.2 mm` | `5.2 mm` | LED hole diameter (sized for 5 mm LEDs; real LEDs are 3 mm -> v3) |
| `led_pitch` | `6.5 mm` | `6.5 mm` | LED 2x2 grid spacing (R, G, Y, IR) |
| `win` | `8 mm` | `8 mm` | Sensor window size (square), TCS34725 / TSL2591 |
| `cap_wall` | — | `3 mm` | Cap wall and top thickness |
| `cap_r` | — | `5 mm` | Cap corner radius seen from above (must be > cap_top_r) |
| `cap_top_r` | — | `3 mm` | Cap top-edge roundover (keep <= cap_wall) |
| `knob_d` | — | `12 mm` | Cap knob diameter |
| `knob_h` | — | `7 mm` | Cap knob height |
| `knob_r` | — | `2 mm` | Knob top and base roundover |
| `usb_w` | `13 mm` | `13 mm` | USB-C cutout width (fits the cable's plug housing) |
| `usb_h` | `8 mm` | `8 mm` | USB-C cutout height |
| `usb_z` | `14 mm` | `14 mm` | USB-C cutout centre height above the floor (ESP32 on breadboard) |
| `lcd_bw` | — | `71.3 mm` | LCD bezel (metal frame) width X - measure |
| `lcd_bh` | — | `26.3 mm` | LCD bezel height Y - measure |
| `lcd_fit` | — | `0.25 mm` | Window clearance per side around the bezel (snug = light-tight) |
| `lcd_bz_t` | — | `7 mm` | Bezel top above the LCD PCB top surface - measure |
| `lcd_pcb_w` | — | `80 mm` | LCD PCB width X |
| `lcd_pcb_h` | — | `36 mm` | LCD PCB height Y |
| `lcd_pcb_t` | — | `1.6 mm` | LCD PCB thickness |
| `lcd_dx` | `75 mm` | `75 mm` | LCD mounting hole spacing X |
| `lcd_dy` | `31 mm` | `31 mm` | LCD mounting hole spacing Y |
| `lcd_hole` | `3.2 mm` | `2.8 mm` | LCD screw holes in the lid (M2.5; the PCB holes are 2.5 mm) |
| `seal_t` | — | `1.6 mm` | LCD light-seal skirt wall thickness |
| `seal_lip` | — | `1 mm` | Width of the ledge the LCD PCB is pulled up against |
| `box_l` | `#bb_len + 2 * #bb_gap + 2 * #wall` | `#bb_len + 2 * #bb_gap + 2 * #wall` | (derived) Outer length X |
| `box_w` | `#optics_d + #bb_wid + #bb_gap + 2 * #wall` | `#optics_d + #part_t + #bb_wid + #bb_gap + #post_s + 2 * #wall` | (derived) Outer width Y (back corner posts sit behind the breadboard) |
| `base_h` | `#floor_t + #in_h` | `#floor_t + #in_h` | (derived) Base height |
| `bb_cy` | `#wall + #optics_d + #bb_wid / 2` | `#wall + #optics_d + #part_t + #bb_wid / 2` | (derived) Breadboard centre Y (USB-C lines up on it) |
| `post_c` | — | `#wall + #post_s / 2` | (derived) Insert/screw centre distance from the outer edges |
| `cuv_cx` | `#box_l / 2` | `#box_l / 2` | Cuvette centre X (default: centred) |
| `cuv_cy` | `#wall + #optics_d / 2` | `#wall + #optics_d / 2` | Cuvette centre Y (default: middle of optics zone) |
| `cuv_hole` | `#cuv_w + 2 * #cuv_fit` | `#cuv_w + 2 * #cuv_fit` | (derived) Cuvette hole size |
| `ch_h` | `#in_h + #lid_t + #collar` | `#in_h + #lid_t + #collar` | (derived) Chamber height above floor |
| `ch_x0` | `#cuv_cx - #cuv_hole / 2 - #led_wall` | `#cuv_cx - #cuv_hole / 2 - #led_wall` | (derived) Chamber min X (LED face) |
| `ch_x1` | `#cuv_cx + #cuv_hole / 2 + #ch_wall` | `#cuv_cx + #cuv_hole / 2 + #ch_wall` | (derived) Chamber max X (180 deg sensor face) |
| `ch_y0` | `#cuv_cy - #cuv_hole / 2 - #ch_wall` | `#cuv_cy - #cuv_hole / 2 - #ch_wall` | (derived) Chamber min Y |
| `ch_y1` | `#cuv_cy + #cuv_hole / 2 + #ch_wall` | `#cuv_cy + #cuv_hole / 2 + #ch_wall` | (derived) Chamber max Y (90 deg sensor face) |
| `pocket` | `#cuv_h - #cuv_grab` | `#cuv_h - #cuv_grab` | (derived) Cuvette pocket depth |
| `beam_z` | `#floor_t + #ch_h - #pocket + #beam_h` | `#floor_t + #ch_h - #pocket + #beam_h` | (derived) Beam height from the bottom of the base |
| `cap_h` | — | `#collar + #cuv_grab + 1 mm + #cap_wall` | (derived) Cap height above the lid (without knob) |
| `lcd_cy` | — | `#bb_cy` | LCD centre Y (default: over the breadboard) |
| `lcd_drop` | — | `#lcd_bz_t - #lid_t` | (derived) LCD PCB top below the lid underside (bezel flush with lid top) |
| `lcd_w` | `72 mm` | — | LCD window width (bezel pokes through) |
| `lcd_h` | `25 mm` | — | LCD window height |

---

## Appendix B. Input and decision log

The team's inputs and decisions, in order, and where each one is used in this document.

| Date | Input or decision | Where |
|---|---|---|
| 2026-11-06 | Project root set up: Onshape MCP copied from `~/Workspace/aicad` and tested; Anthropic API key stored in the root `.env`. AWS tooling was set up and removed the same night (nothing was deployed). | CLAUDE.md |
| 2026-11-07 | Project context: SuppBuddy, inspired by HackMIT's Peel. An iPhone-powered supplement tester; optical test + label photo + crowdsourced database + brand reputation → an agent's verdict. | §1, CLAUDE.md |
| 2026-11-07 | Design brief: cuvette, three LEDs + IR, standard ESP32, LCD, TCS34725 (CJMCU-34725) + TSL2591, all on a breadboard, USB-C exposed. Simple, editable, quick to print, parametric. | §1.2, V1 |
| 2026-11-07 | CAD only in this repo for now; teammates build the rest. | §1.1 |
| 2026-11-07 | LCD: a HiLetgo HD44780 1602 (blue backlight, 5 V). | §5.7 |
| 2026-11-07 | Hide all the planes in Onshape. | §2 |
| 2026-11-07 | V1 feedback and the V2 change list: inserts (0.19 in OD × 0.15 in), rounded cap, light-tight LCD, light wall at the USB port. Save V1 first, then V2. | §3 V1, V2 |
| 2026-11-07 | Sensor boards: Adafruit TCS34725 and EC Buying TSL2591 (with the listing PDF). LEDs: four small ones, 0.12 in body / 0.15 in lip / 0.2 in long. Better sensor and LED mounting, perhaps with inserts, goes into V3. Start this document. | §5.3–§5.5, V3 |
| 2026-11-07 | V2 approved. Switch to SKS 20 mL vials (about 1 in across, solid white cap). | §3, §5.8 |
| 2026-11-07 | Light-seal ideas: the vial sticking out with a cap over it, or a printed piece on the white cap. | V3 decisions |
| 2026-11-07 | Line the LEDs up vertically for a round vial. | V3, §6 |
| 2026-11-07 | Chosen: printed cap sleeve, V3 scope with sensor mounts, slide-in pockets. Vial calipers: body 27.4, cap 24.7, 60 tall with the cap. | V3 decisions |
| 2026-11-07 | LED correction: 4.6 mm body, 5.3 mm lip. | §5.3 |
| 2026-11-07 | Onshape rate limit: use Onshape in the team's browser instead. The browser was used for viewing and reading errors, and the rebuild moved to FeatureScript. | §2, V3 |
| 2026-11-07 | V3 saved; this document created. | — |
| 2026-11-08 | Visually appealing slide graphics of the CAD in a few styles; then CAD sketches or blueprint drawings instead of full renders. | §9 |
| 2026-11-08 | Review this document so that no context is lost. | Appendix C |
| 2026-11-08 | Make three Part Studios in Onshape, one per iteration (V1, V2, V3). Then, using the API sparingly, make V3 "a proper cad instead of the featurescript thing". | §2, §3 V3 |
| 2026-11-08 | Move the project into `hardware/` of the SuppBuddy monorepo (`git@github.com:dzwangg/SuppBuddy.git`). Commit only `cad/`, `ideas.md` and `details.md`, and make no commits until asked. | CLAUDE.md |

---

## Appendix C. Document history

- **2026-11-07:** created with V3. It covered versions V1–V3, the parameter reference, hardware,
  optics, printing, open items and Appendix A.
- **2026-11-08:** reviewed against `cad/build_fs.py`, the saved versions and the full project
  session record. All 69 parameter rows match `GROUPS`, and the derived numbers were recomputed.
  - Added:
    - the design brief and scope (§1.1, §1.2);
    - the BOM element ID and the state of Main (§2);
    - V1 design reasons and the team's V1 feedback;
    - the V3 decision table and how V3 was built (incl. the wipe of V2's features from Main);
    - the full derived-value list (§4);
    - a parts list (§5.0);
    - sources and listings for the sensors, LCD and vial;
    - the LCD PCB-width risk (§5.7);
    - TCS34725 availability (§5.5);
    - the LED-type note (§5.3);
    - STL export (§7);
    - presentation graphics (§9);
    - Appendices B and C.
  - Corrected:
    - the slit's chord variation (about 0.3 %, 0.31 % at d = 1; it said "less than 0.3 %");
    - the slit's role (it limits where light enters the bore);
    - the vial numbers, which are the team's caliper readings: the SKS page lists none.
- **2026-11-08, second check:** re-checked by Claude and, separately, by an independent reviewer
  agent. The sources were the exported V3 STLs, the datasheets and listing saved during the project,
  Adafruit's fab prints and the session record. Every reviewer finding was checked against those
  sources before it was applied.
  - Confirmed:
    - 112 geometry probe points, the STL boxes and volumes;
    - the LCD numbers against the GDM1602K drawing (80 × 36 × 1.6, holes ⌀2.5 at 75 × 31, bezel
      71.3 × 26.3);
    - the TCS34725 header order and chip position against Adafruit's fab print;
    - the "Parent Id" error text against the screenshot of Onshape's notices panel;
    - the IDs across both docs and the scripts.
  - Added:
    - the part-to-part interference check from the STLs (§3 V3);
    - iOS has no Web Bluetooth, so BLE needs a native app (§5.2);
    - a test for LED light leaks (§5.3);
    - the TSL2591's possible second address 0x28, and the slot play for a 1 mm board (§5.4);
    - the SKS page's stock notice (§5.8);
    - the missing sleeve knob (§3 V3) and more board measurements (§8).
  - Corrected:
    - Adafruit #1980's pin order (VIN, 3Vo, GND, SCL, SDA, INT; it said VIN, GND, 3Vo, …);
    - the TSL2591 supply range (3.3–5 V) and where its pin list comes from (§5.4);
    - the LCD backlight figures, which differ between the two datasheets (§5.7);
    - 3.3 V logic into the LCD: out of spec on paper (VIH ≥ 0.7·VDD), not "reliable" (§5.7);
    - the vertical-spread angles: the ray that reaches the chip runs about 17.2° in air and 12.8° in
      water, +2.5 %. It had refracted the straight-line 13.8° instead (§6);
    - the fill volumes (about 16 mL to the line; it said 15–16, and "14 mL covers the LED
      centres", which is the slit top);
    - the failed REST rebuild: it left Part Studio 1 empty (it said "partway through");
    - the browser 401: an XSRF token is the likely cause, not a confirmed one;
    - wall thicknesses in §5.12 (inner walls are 1.2–1.6, not 2+);
    - quotes made exact or unquoted;
    - the order of Appendix B;
    - who suggested the AS7341 (Claude, not the team);
    - which mesh dumps include the USB-C plug;
    - wording about the TCS34725's orientation, the CJMCU outline, the USB cutout fit and the LCD
      sources.
- **2026-11-08, evening (CAD, Onshape):**
  - One Part Studio per iteration: DeviceHolder V1 and V2 copied from their versions, and
    DeviceHolder V3 rebuilt as an ordinary feature tree by the new `cad/build_v3.py` (§2; §3, "V3
    rebuilt as a feature tree").
  - The old FeatureScript studio was renamed. The §2 tables now list the hand-made "v3 drawings" tab
    and record that Assembly 1, its BOM and zz_api_probe were deleted.
  - Verified: V1 and V2 copies have 77 and 119 features, all OK. DeviceHolder V3's part volumes and
    areas match the FeatureScript model.
