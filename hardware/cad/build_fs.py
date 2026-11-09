"""Build the SuppBuddy enclosure (v3 onward) in Onshape as ONE custom FeatureScript feature.

v1/v2 were built feature by feature over the REST API (cad/build_enclosure.py). That costs about
150 API calls per rebuild and ran into Onshape's per-user daily API limits. From v3 on, the whole
enclosure is a FeatureScript program in the "SuppBuddy FeatureScript" tab, and Part Studio 1 holds
a single "SuppBuddy enclosure" feature. Every dimension is a parameter of that feature. In Onshape,
double-click the feature, change values (they're grouped), and press the green check. A rebuild
with this script costs about 4 API calls.

The FeatureScript source is generated from GROUPS (parameters, defaults, limits) plus TEMPLATE
(geometry) below, and is also written to cad/suppbuddy_enclosure.fs for reading. Edit this file and
re-run it, not the Onshape tab: a re-run overwrites the tab.

Usage:  onshape-mcp/.venv/Scripts/python.exe cad/build_fs.py             push code, add/update the feature
        onshape-mcp/.venv/Scripts/python.exe cad/build_fs.py --dry-run   only write cad/suppbuddy_enclosure.fs
        onshape-mcp/.venv/Scripts/python.exe cad/build_fs.py --set vial_d=28 beam_h=20   (one-off values)
"""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osh  # noqa: E402

DID = "ada0757f8a367ed8c935f14f"
WID = "389f688fe28c85a3add01f94"
EID = "5da49a2f1204f18bc3cad3cc"  # Part Studio 1
HERE = Path(__file__).resolve().parent
STATE = HERE / ".fs_state.json"  # {"feature_studio": element id, "feature_id": feature id in Part Studio 1}
FS_FILE = HERE / "suppbuddy_enclosure.fs"
MODEL_VERSION = "v3"
FEATURE_TYPE = "suppBuddyEnclosure"

# (group, [(parameter id, dialog label, default mm, min mm, max mm), ...]). Every value is in mm.
GROUPS = [
    ("Print and fit", [
        ("wall", "Base outer wall", 2, 0.8, 10),
        ("floor_t", "Base floor", 2, 0.8, 10),
        ("lid_t", "Lid thickness", 2, 0.8, 10),
        ("fit", "Clearance per side (lid hole, sleeve skirt, LCD PCB)", 0.3, 0, 2),
        ("corner_r", "Outer corner radius (keep > wall)", 4, 0, 20),
    ]),
    ("Lid screws (M3 heat-set inserts)", [
        ("post_s", "Corner post size", 9, 5, 20),
        ("insert_d", "Insert hole diameter (M3 insert OD ~4.8)", 4.2, 2, 8),
        ("insert_depth", "Insert hole depth", 7, 2, 30),
        ("screw_d", "Lid screw clearance hole", 3.4, 2, 6),
    ]),
    ("Electronics bay", [
        ("bb_len", "Breadboard length X (half-size ~83)", 84, 20, 300),
        ("bb_wid", "Breadboard width Y", 55, 20, 200),
        ("bb_gap", "Clearance around the breadboard", 2, 0, 20),
        ("in_h", "Interior height, floor to rim", 40, 10, 150),
        ("part_t", "Light wall thickness (optics vs bay)", 1.6, 0.8, 10),
        ("wire_w", "Wire notch width (top of light wall)", 24, 1, 100),
        ("wire_h", "Wire notch depth", 10, 1, 50),
    ]),
    ("Sample vial (SKS 20 mL, measured)", [
        ("vial_d", "Vial body diameter", 27.4, 5, 60),
        ("vial_h", "Vial height with cap", 60, 20, 150),
        ("vcap_d", "Vial cap diameter", 24.7, 5, 60),
        ("vcap_h", "Cap height gripped by the sleeve", 10, 2, 40),
        ("vial_fit", "Vial-to-bore clearance per side", 0.4, 0, 3),
        ("vial_z", "Vial bottom above the floor", 0, 0, 30),
        ("front_gap", "Gap between front wall and optics block", 3, 0, 30),
        ("vial_dx", "Vial X offset from centre", 0, -100, 100),
    ]),
    ("Optics block and LEDs", [
        ("ch_wall", "Wall at the sensor windows / collar wall", 2.5, 0.8, 10),
        ("led_wall", "LED-side wall (LED holes + slit)", 9, 4, 30),
        ("beam_h", "LED column centre above the vial bottom", 18, 5, 60),
        ("led_d", "LED hole diameter (body 4.6, lip 5.3)", 4.8, 1, 12),
        ("led_pitch", "LED vertical spacing", 6, 2, 20),
        ("led_depth", "LED hole depth (LED 5.1 long with lip)", 5, 1, 20),
        ("slit_w", "Slit aperture width", 2, 0.5, 10),
        ("win", "Sensor window size (square)", 5, 1, 15),
    ]),
    ("Sensor pockets (slide-in boards)", [
        ("pk_s", "Gap from block face to board (its parts)", 1.5, 0, 10),
        ("pk_t", "Board slot width", 2, 0.8, 5),
        ("pk_lip", "Rail overlap on each board edge", 1, 0.3, 5),
        ("pk_back", "Back rail lip", 1.2, 0.6, 5),
        ("pk_side", "Rail side wall", 1.5, 0.6, 5),
        ("pk_cl", "Board edge clearance per side", 0.3, 0, 2),
        ("pk_hz", "Free strip at the board top (header pins)", 4, 0, 20),
        ("tcs_room", "Room behind the 90 deg board (header + plugs)", 16, 0, 60),
        ("tsl_w", "TSL2591 board width", 16, 5, 50),
        ("tsl_h", "TSL2591 board height (header edge up)", 19, 5, 50),
        ("tsl_sz", "TSL2591 chip centre above board bottom (measure)", 9.5, 0, 50),
        ("tsl_su", "TSL2591 chip offset from board centre (+Y)", 0, -20, 20),
        ("tcs_w", "TCS34725 board width", 20.4, 5, 50),
        ("tcs_h", "TCS34725 board height (header edge up)", 20.4, 5, 50),
        ("tcs_sz", "TCS34725 chip centre above board bottom", 10.4, 0, 50),
        ("tcs_su", "TCS34725 chip offset from board centre (+X)", 0, -20, 20),
    ]),
    ("Vial cap sleeve", [
        ("sl_wall", "Skirt wall", 2, 0.8, 10),
        ("sl_top", "Roof above the vial cap", 3, 0.8, 20),
        ("sl_r", "Top edge roundover", 1.5, 0, 10),
        ("sk_gap", "Air gap between skirt and lid (vial seated)", 1.5, 0, 20),
        ("vcap_fit", "Cap pocket = cap diameter + this (press fit)", 0.1, -1, 2),
    ]),
    ("USB-C", [
        ("usb_w", "Cutout width", 13, 2, 40),
        ("usb_h", "Cutout height", 8, 2, 30),
        ("usb_z", "Cutout centre above the floor", 14, 0, 100),
    ]),
    ("LCD (HD44780 1602, measure yours)", [
        ("lcd_bw", "Bezel width X", 71.3, 10, 200),
        ("lcd_bh", "Bezel height Y", 26.3, 5, 100),
        ("lcd_fit", "Window clearance per side", 0.25, 0, 3),
        ("lcd_bz_t", "Bezel top above PCB top (keep > lid)", 7, 2, 20),
        ("lcd_pcb_w", "PCB width X", 80, 10, 200),
        ("lcd_pcb_h", "PCB height Y", 36, 5, 100),
        ("lcd_pcb_t", "PCB thickness", 1.6, 0.5, 5),
        ("lcd_dx", "Mounting hole spacing X", 75, 5, 200),
        ("lcd_dy", "Mounting hole spacing Y", 31, 5, 100),
        ("lcd_hole", "Mounting screw hole (M2.5)", 2.8, 1, 6),
        ("seal_t", "Light-seal skirt wall", 1.6, 0.8, 5),
        ("seal_lip", "Ledge under the PCB edge", 1, 0.3, 5),
        ("lcd_off", "LCD Y offset from the breadboard centre", 0, -100, 100),
    ]),
]

TEMPLATE = r"""FeatureScript @VERSION@;
import(path : "onshape/std/geometry.fs", version : "@VERSION@.0");

// SuppBuddy enclosure (@MODEL@). GENERATED by cad/build_fs.py in the project repo: edit that file and
// re-run it; edits made here are overwritten. Three parts, modelled in their assembled positions:
//   Base            - open box: electronics bay (breadboard + ESP32, USB-C cutout) behind a light wall;
//                     in front, the optics block: vial bore, vertical LED column + slit aperture, sensor
//                     windows at 180 deg (TSL2591) and 90 deg (TCS34725) with slide-in board pockets, and
//                     a round collar that pokes up through the lid. 4 corner posts take M3 heat-set inserts.
//   Lid             - plate: collar hole, LCD bezel window + light-seal ledge/skirt, M3 screw holes.
//   Vial cap sleeve - cup that presses onto the vial's white cap; seated, its skirt covers the collar.
// Axes: X = length (left->right), Y = depth (front->back), Z = up. Origin = outer front-left-bottom corner.

function sbBox(context is Context, id is Id, x0, y0, z0, x1, y1, z1)
{
    fCuboid(context, id, { "corner1" : vector(x0, y0, z0), "corner2" : vector(x1, y1, z1) });
}

function sbCylZ(context is Context, id is Id, cx, cy, z0, z1, dia)
{
    fCylinder(context, id, { "bottomCenter" : vector(cx, cy, z0), "topCenter" : vector(cx, cy, z1), "radius" : dia / 2 });
}

function sbCylX(context is Context, id is Id, x0, x1, cy, cz, dia)
{
    fCylinder(context, id, { "bottomCenter" : vector(x0, cy, cz), "topCenter" : vector(x1, cy, cz), "radius" : dia / 2 });
}

// Round the vertical (Z) edges of a body.
function sbRoundVertical(context is Context, id is Id, body is Query, r)
{
    if (r < 0.01 * millimeter)
        return;
    var edges = [];
    for (var e in evaluateQuery(context, qGeometry(qOwnedByBody(body, EntityType.EDGE), GeometryType.LINE)))
    {
        if (abs(evLine(context, { "edge" : e }).direction[2]) > 0.999)
            edges = append(edges, e);
    }
    opFillet(context, id, { "entities" : qUnion(edges), "radius" : r });
}

// Round the edges lying in the top plane of a body.
function sbRoundTop(context is Context, id is Id, body is Query, r)
{
    if (r < 0.01 * millimeter)
        return;
    const zt = evBox3d(context, { "topology" : body, "tight" : true }).maxCorner[2];
    var edges = [];
    for (var e in evaluateQuery(context, qOwnedByBody(body, EntityType.EDGE)))
    {
        const b = evBox3d(context, { "topology" : e, "tight" : true });
        if (abs(b.minCorner[2] - zt) < 0.0001 * millimeter && abs(b.maxCorner[2] - zt) < 0.0001 * millimeter)
            edges = append(edges, e);
    }
    opFillet(context, id, { "entities" : qUnion(edges), "radius" : r });
}

function sbUnite(context is Context, id is Id, bodies is Query)
{
    if (size(evaluateQuery(context, bodies)) > 1)
        opBoolean(context, id, { "tools" : bodies, "operationType" : BooleanOperationType.UNION });
}

function sbCut(context is Context, id is Id, target is Query, tools is Query)
{
    opBoolean(context, id, { "targets" : target, "tools" : tools, "operationType" : BooleanOperationType.SUBTRACTION });
}

annotation { "Feature Type Name" : "SuppBuddy enclosure",
             "Feature Type Description" : "SuppBuddy vial tester enclosure: base, lid and vial cap sleeve. All sizes in mm." }
export const suppBuddyEnclosure = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
@PRECONDITION@
    }
    {
        const d = definition;
        const mm = millimeter;
        const zero = 0 * mm;

        // ---------------- derived dimensions
        const bore = d.vial_d + 2 * d.vial_fit;                          // vial bore diameter
        const pk_depth = d.pk_s + d.pk_t + d.pk_back;                    // sensor pocket depth off the block face
        const optics_d = d.front_gap + bore + 2 * d.ch_wall + pk_depth + d.tcs_room; // optics zone depth (Y)
        const box_l = d.bb_len + 2 * d.bb_gap + 2 * d.wall;              // outer length X
        const box_w = optics_d + d.part_t + d.bb_wid + d.bb_gap + d.post_s + 2 * d.wall; // outer width Y
        const base_h = d.floor_t + d.in_h;                               // base height (rim)
        const bb_cy = d.wall + optics_d + d.part_t + d.bb_wid / 2;       // breadboard centre Y (USB-C on it)
        const post_c = d.wall + d.post_s / 2;                            // screw centre from the outer edges
        const vial_cx = box_l / 2 + d.vial_dx;
        const vial_cy = d.wall + d.front_gap + d.ch_wall + bore / 2;
        const ch_x0 = vial_cx - bore / 2 - d.led_wall;                   // optics block: LED face
        const ch_x1 = vial_cx + bore / 2 + d.ch_wall;                    // optics block: 180 deg sensor face
        const ch_y0 = vial_cy - bore / 2 - d.ch_wall;
        const ch_y1 = vial_cy + bore / 2 + d.ch_wall;                    // optics block: 90 deg sensor face
        const vial_z0 = d.floor_t + d.vial_z;                            // vial bottom
        const beam_z = vial_z0 + d.beam_h;                               // LED column centre
        const collar_d = bore + 2 * d.ch_wall;
        const collar_top = vial_z0 + d.vial_h - d.vcap_h - 1 * mm;       // collar ends just below the gripped cap
        const sk_z = base_h + d.lid_t + d.sk_gap;                        // sleeve skirt bottom
        const sl_top_z = vial_z0 + d.vial_h + d.sl_top;                  // sleeve top
        const sl_d = collar_d + 2 * (d.fit + d.sl_wall);                 // sleeve outer diameter
        const tsl_z0 = beam_z - d.tsl_sz;                                // TSL2591 board bottom edge
        const tcs_z0 = beam_z - d.tcs_sz;                                // TCS34725 board bottom edge
        const tsl_yc = vial_cy - d.tsl_su;                               // board centre so the chip is on the beam
        const tcs_xc = vial_cx - d.tcs_su;
        const tsl_bw = d.tsl_w + 2 * (d.pk_cl + d.pk_side);
        const tcs_bw = d.tcs_w + 2 * (d.pk_cl + d.pk_side);
        const tsl_top = tsl_z0 + d.tsl_h - d.pk_hz;                      // rails stop below the header strip
        const tcs_top = tcs_z0 + d.tcs_h - d.pk_hz;
        const lcd_cx = box_l / 2;
        const lcd_cy = bb_cy + d.lcd_off;
        const lcd_drop = d.lcd_bz_t - d.lid_t;                           // PCB top below the lid underside
        const seal_w = d.lcd_pcb_w + 2 * (d.fit + d.seal_t);
        const seal_h = d.lcd_pcb_h + 2 * (d.fit + d.seal_t);
        const corners = [[post_c, post_c], [post_c, box_w - post_c], [box_l - post_c, post_c], [box_l - post_c, box_w - post_c]];

        if (lcd_drop <= zero)
            throw regenError("LCD bezel height must be larger than the lid thickness", ["lcd_bz_t"]);
        if (collar_top <= base_h + d.lid_t)
            throw regenError("Vial too short: the collar would not reach above the lid", ["vial_h"]);
        if (tsl_z0 < d.floor_t || tcs_z0 < d.floor_t)
            throw regenError("A sensor board would sit below the floor: raise the LED column", ["beam_h"]);

        // ======================== Base
        // (Onshape needs all operations under one Id prefix to be contiguous, so each part is tracked as
        // the union of the bodies its pieces were created by.)
        const shellQ = qCreatedBy(id + "shell", EntityType.BODY);
        const baseQ = qUnion([shellQ, qCreatedBy(id + "bp", EntityType.BODY)]);
        const cavQ = qCreatedBy(id + "cav", EntityType.BODY);
        sbBox(context, id + "shell", zero, zero, zero, box_l, box_w, base_h);
        sbRoundVertical(context, id + "outerRound", shellQ, d.corner_r);
        sbBox(context, id + "cav", d.wall, d.wall, d.floor_t, box_l - d.wall, box_w - d.wall, base_h + 1 * mm);
        sbRoundVertical(context, id + "cavRound", cavQ, d.corner_r - d.wall);
        sbCut(context, id + "cavCut", shellQ, cavQ);

        for (var i = 0; i < 4; i += 1)   // corner posts for the M3 heat-set inserts
        {
            const px = corners[i][0] - d.post_s / 2;
            const py = corners[i][1] - d.post_s / 2;
            sbBox(context, id + "bp" + ("post" ~ toString(i)), px, py, d.floor_t, px + d.post_s, py + d.post_s, base_h);
        }
        sbBox(context, id + "bp" + "lightWall", d.wall, d.wall + optics_d, d.floor_t, box_l - d.wall, d.wall + optics_d + d.part_t, base_h);
        sbBox(context, id + "bp" + "optics", ch_x0, ch_y0, d.floor_t, ch_x1, ch_y1, base_h);
        sbCylZ(context, id + "bp" + "collar", vial_cx, vial_cy, base_h, collar_top, collar_d);
        sbBox(context, id + "bp" + "tslPocket", ch_x1, tsl_yc - tsl_bw / 2, d.floor_t, ch_x1 + pk_depth, tsl_yc + tsl_bw / 2, tsl_top);
        sbBox(context, id + "bp" + "tcsPocket", tcs_xc - tcs_bw / 2, ch_y1, d.floor_t, tcs_xc + tcs_bw / 2, ch_y1 + pk_depth, tcs_top);
        sbUnite(context, id + "baseUnion", baseQ);

        for (var i = 0; i < 4; i += 1)   // heat-set insert holes
        {
            sbCylZ(context, id + "bn" + ("insert" ~ toString(i)), corners[i][0], corners[i][1], base_h - d.insert_depth, base_h + 1 * mm, d.insert_d);
        }
        sbBox(context, id + "bn" + "wireNotch", vial_cx - d.wire_w / 2, d.wall + optics_d - 1 * mm, base_h - d.wire_h,
              vial_cx + d.wire_w / 2, d.wall + optics_d + d.part_t + 1 * mm, base_h + 1 * mm);
        sbCylZ(context, id + "bn" + "bore", vial_cx, vial_cy, vial_z0, collar_top + 1 * mm, bore);
        // LEDs: one vertical column in the plane through the vial axis, so every beam crosses the full
        // diameter at normal incidence. Each LED is pushed in from the -X face until its lip stops it;
        // a vertical slit then limits the beam to the axis plane but lets every LED reach the 180 deg sensor.
        const ks = [-1.5, -0.5, 0.5, 1.5];
        for (var i = 0; i < 4; i += 1)
        {
            sbCylX(context, id + "bn" + ("led" ~ toString(i)), ch_x0 - 1 * mm, ch_x0 + d.led_depth, vial_cy, beam_z + ks[i] * d.led_pitch, d.led_d);
        }
        const slit_h = 3 * d.led_pitch + d.led_d;
        sbBox(context, id + "bn" + "slit", ch_x0 + d.led_depth, vial_cy - d.slit_w / 2, beam_z - slit_h / 2,
              ch_x0 + d.led_wall + 1 * mm, vial_cy + d.slit_w / 2, beam_z + slit_h / 2);
        sbBox(context, id + "bn" + "win180", vial_cx + bore / 2 - 2 * mm, vial_cy - d.win / 2, beam_z - d.win / 2,
              ch_x1 + 1 * mm, vial_cy + d.win / 2, beam_z + d.win / 2);
        sbBox(context, id + "bn" + "win90", vial_cx - d.win / 2, vial_cy + bore / 2 - 2 * mm, beam_z - d.win / 2,
              vial_cx + d.win / 2, ch_y1 + 1 * mm, beam_z + d.win / 2);
        // Slide-in pockets: slot for the board + clearance for its parts in front + open back, leaving
        // C-shaped rails on the board edges and a solid stop under the board's bottom edge.
        const tslIn = d.tsl_w / 2 - d.pk_lip;
        sbBox(context, id + "bn" + "tslSlot", ch_x1 + d.pk_s, tsl_yc - d.tsl_w / 2 - d.pk_cl, tsl_z0,
              ch_x1 + d.pk_s + d.pk_t, tsl_yc + d.tsl_w / 2 + d.pk_cl, tsl_top + 1 * mm);
        sbBox(context, id + "bn" + "tslFront", ch_x1, tsl_yc - tslIn, tsl_z0, ch_x1 + d.pk_s + 0.1 * mm, tsl_yc + tslIn, tsl_top + 1 * mm);
        sbBox(context, id + "bn" + "tslBack", ch_x1 + d.pk_s + d.pk_t - 0.1 * mm, tsl_yc - tslIn, tsl_z0,
              ch_x1 + pk_depth + 1 * mm, tsl_yc + tslIn, tsl_top + 1 * mm);
        const tcsIn = d.tcs_w / 2 - d.pk_lip;
        sbBox(context, id + "bn" + "tcsSlot", tcs_xc - d.tcs_w / 2 - d.pk_cl, ch_y1 + d.pk_s, tcs_z0,
              tcs_xc + d.tcs_w / 2 + d.pk_cl, ch_y1 + d.pk_s + d.pk_t, tcs_top + 1 * mm);
        sbBox(context, id + "bn" + "tcsFront", tcs_xc - tcsIn, ch_y1, tcs_z0, tcs_xc + tcsIn, ch_y1 + d.pk_s + 0.1 * mm, tcs_top + 1 * mm);
        sbBox(context, id + "bn" + "tcsBack", tcs_xc - tcsIn, ch_y1 + d.pk_s + d.pk_t - 0.1 * mm, tcs_z0,
              tcs_xc + tcsIn, ch_y1 + pk_depth + 1 * mm, tcs_top + 1 * mm);
        sbBox(context, id + "bn" + "usb", -1 * mm, bb_cy - d.usb_w / 2, d.floor_t + d.usb_z - d.usb_h / 2,
              d.wall + 1 * mm, bb_cy + d.usb_w / 2, d.floor_t + d.usb_z + d.usb_h / 2);
        sbCut(context, id + "baseCut", baseQ, qCreatedBy(id + "bn", EntityType.BODY));

        // ======================== Lid
        const plateQ = qCreatedBy(id + "lidPlate", EntityType.BODY);
        const lidQ = qUnion([plateQ, qCreatedBy(id + "lidSeal", EntityType.BODY)]);
        sbBox(context, id + "lidPlate", zero, zero, base_h, box_l, box_w, base_h + d.lid_t);
        sbRoundVertical(context, id + "lidRound", plateQ, d.corner_r);
        sbBox(context, id + "lidSeal", lcd_cx - seal_w / 2, lcd_cy - seal_h / 2, base_h - lcd_drop - d.lcd_pcb_t,
              lcd_cx + seal_w / 2, lcd_cy + seal_h / 2, base_h);
        sbUnite(context, id + "lidUnion", lidQ);
        // LCD light seal: the PCB sits in the skirt, pulled up against the ledge by its 4 screws, so the
        // only way in is the snug bezel window, which the bezel itself fills.
        const lz0 = base_h - lcd_drop - d.lcd_pcb_t - 1 * mm;
        sbBox(context, id + "ln" + "ledgeOpening", lcd_cx - d.lcd_pcb_w / 2 + d.seal_lip, lcd_cy - d.lcd_pcb_h / 2 + d.seal_lip, lz0,
              lcd_cx + d.lcd_pcb_w / 2 - d.seal_lip, lcd_cy + d.lcd_pcb_h / 2 - d.seal_lip, base_h);
        sbBox(context, id + "ln" + "pcbPocket", lcd_cx - d.lcd_pcb_w / 2 - d.fit, lcd_cy - d.lcd_pcb_h / 2 - d.fit, lz0,
              lcd_cx + d.lcd_pcb_w / 2 + d.fit, lcd_cy + d.lcd_pcb_h / 2 + d.fit, base_h - lcd_drop);
        sbBox(context, id + "ln" + "window", lcd_cx - d.lcd_bw / 2 - d.lcd_fit, lcd_cy - d.lcd_bh / 2 - d.lcd_fit, base_h - 1 * mm,
              lcd_cx + d.lcd_bw / 2 + d.lcd_fit, lcd_cy + d.lcd_bh / 2 + d.lcd_fit, base_h + d.lid_t + 1 * mm);
        sbCylZ(context, id + "ln" + "collarHole", vial_cx, vial_cy, base_h - 1 * mm, base_h + d.lid_t + 1 * mm, collar_d + 2 * d.fit);
        const sx = [-1, 1, -1, 1];
        const sy = [-1, -1, 1, 1];
        for (var i = 0; i < 4; i += 1)
        {
            sbCylZ(context, id + "ln" + ("lcdHole" ~ toString(i)), lcd_cx + sx[i] * d.lcd_dx / 2, lcd_cy + sy[i] * d.lcd_dy / 2,
                   base_h - 1 * mm, base_h + d.lid_t + 1 * mm, d.lcd_hole);
            sbCylZ(context, id + "ln" + ("screw" ~ toString(i)), corners[i][0], corners[i][1], base_h - 1 * mm, base_h + d.lid_t + 1 * mm, d.screw_d);
        }
        sbCut(context, id + "lidCut", lidQ, qCreatedBy(id + "ln", EntityType.BODY));

        // ======================== Vial cap sleeve
        const slQ = qCreatedBy(id + "sleeve", EntityType.BODY);
        sbCylZ(context, id + "sleeve", vial_cx, vial_cy, sk_z, sl_top_z, sl_d);
        sbRoundTop(context, id + "slRound", slQ, d.sl_r);
        sbCylZ(context, id + "sn" + "skirt", vial_cx, vial_cy, sk_z - 1 * mm, collar_top + 1 * mm, collar_d + 2 * d.fit);
        sbCylZ(context, id + "sn" + "cap", vial_cx, vial_cy, sk_z - 1 * mm, vial_z0 + d.vial_h, d.vcap_d + d.vcap_fit);
        sbCut(context, id + "slCut", slQ, qCreatedBy(id + "sn", EntityType.BODY));

        setProperty(context, { "entities" : baseQ, "propertyType" : PropertyType.NAME, "value" : "Base" });
        setProperty(context, { "entities" : lidQ, "propertyType" : PropertyType.NAME, "value" : "Lid" });
        setProperty(context, { "entities" : slQ, "propertyType" : PropertyType.NAME, "value" : "Vial cap sleeve" });
    });
"""


def precondition():
    out = []
    for group, params in GROUPS:
        out.append(f'        annotation {{ "Group Name" : "{group}", "Collapsed By Default" : true }}')
        out.append("        {")
        for pid, label, default, lo, hi in params:
            out.append(f'            annotation {{ "Name" : "{label}" }}')
            out.append(f"            isLength(definition.{pid}, {{ (millimeter) : [{lo:g}, {default:g}, {hi:g}] }} as LengthBoundSpec);")
        out.append("        }")
    return "\n".join(out)


def source(version):
    return (
        TEMPLATE.replace("@VERSION@", version).replace("@MODEL@", MODEL_VERSION).replace("@PRECONDITION@", precondition())
    )


def values(overrides):
    vals = {pid: default for _, params in GROUPS for pid, _, default, _, _ in params}
    for k, v in overrides.items():
        if k not in vals:
            raise SystemExit(f"unknown parameter {k!r}")
        vals[k] = float(v)
    return vals


def feature(namespace, vals):
    return {
        "btType": "BTMFeature-134",
        "featureType": FEATURE_TYPE,
        "name": f"SuppBuddy enclosure {MODEL_VERSION}",
        "namespace": namespace,
        "parameters": [osh.P_qty(pid, f"{v:g} mm") for pid, v in vals.items()],
    }


async def main():
    overrides = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--set") + 1 :]) if "--set" in sys.argv else {}
    vals = values(overrides)
    if "--dry-run" in sys.argv:
        FS_FILE.write_text(source("0000"), encoding="utf-8")
        print(f"wrote {FS_FILE} ({len(vals)} parameters)")
        return

    S = osh.Studio(DID, WID, EID)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    fs_base = f"/api/v9/featurestudios/d/{DID}/w/{WID}"
    if "feature_studio" not in st:
        r = await S.post(fs_base, data={"name": "SuppBuddy FeatureScript"})
        st["feature_studio"] = r["id"]
        STATE.write_text(json.dumps(st, indent=1))
        print("created Feature Studio", r["id"])
    fse = st["feature_studio"]

    cur = await S.get(f"{fs_base}/e/{fse}")
    m = re.search(r"FeatureScript (\d+);", cur.get("contents") or "")
    if not m:
        raise SystemExit(f"can't find the FeatureScript version in the tab; contents start: {cur.get('contents', '')[:200]!r}")
    src = source(m.group(1))
    FS_FILE.write_text(src, encoding="utf-8")
    if cur["contents"] != src:
        r = await S.post(
            f"{fs_base}/e/{fse}",
            data={
                "contents": src,
                "serializationVersion": cur.get("serializationVersion"),
                "sourceMicroversion": cur.get("sourceMicroversion"),
                "rejectMicroversionSkew": False,
            },
        )
        for n in r.get("notices") or []:
            print("  notice:", n)
        print(f"pushed FeatureScript (std {m.group(1)}, {len(src)} chars)")

    specs = await S.get(f"{fs_base}/e/{fse}/featurespecs")
    spec = next((s for s in specs.get("featureSpecs", []) if s.get("featureType") == FEATURE_TYPE), None)
    if spec is None:
        raise SystemExit(f"feature {FEATURE_TYPE!r} not found: the code probably has an error (open the tab). {specs!r:.600}")
    namespace = spec.get("namespace")
    if not namespace:
        els = await S.get(f"/api/v9/documents/d/{DID}/w/{WID}/elements", params={"elementId": fse})
        namespace = f"e{fse}::m{els[0]['microversionId']}"
    print("namespace:", namespace)

    feat = feature(namespace, vals)
    if "feature_id" in st:
        status = await S.update(st["feature_id"], feat)
        print(f"updated feature {st['feature_id']}: {status}")
    else:
        r = await S.post(S.path + "/features", data={"btType": "BTFeatureDefinitionCall-1406", "feature": feat})
        st["feature_id"] = r["feature"]["featureId"]
        STATE.write_text(json.dumps(st, indent=1))
        status = (r.get("featureState") or {}).get("featureStatus")
        print(f"added feature {st['feature_id']}: {status}")
    if status != "OK":
        raise SystemExit("feature did not regenerate cleanly: open Part Studio 1 and hover the red feature for the error")


if __name__ == "__main__":
    asyncio.run(main())
