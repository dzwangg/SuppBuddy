"""Build the SuppBuddy enclosure (v2) in Onshape (document "SuppBuddy" -> Part Studio 1).

Three printable parts, all driven by Part Studio variables (edit them in the Variable table):
  * Base        - open box. Back: breadboard + ESP32 bay with a USB-C cutout. Front: optics zone with
                  the cuvette chamber (4 LED holes R/G/Y/IR in a 2x2 grid, sensor windows at 180 and
                  90 deg). A light wall (wire notch on top) separates the two zones so light leaking in
                  around the USB-C plug can't reach the optics. 4 corner posts take M3 heat-set inserts.
  * Lid         - flat plate: chamber-collar hole, snug 1602 LCD bezel window, an LCD light-seal skirt
                  underneath (the LCD PCB is screwed up against its ledge), and 4 M3 screw holes.
  * Cuvette cap - rounded cup with a knob; slides over the chamber collar to block ambient light.

History: Onshape version "V1" = first box (v1 of this script). This file builds v2. See details.md.
Axes: X = length (left->right), Y = depth (front->back), Z = up. Origin = outer front-left-bottom corner.
Usage:  onshape-mcp/.venv/Scripts/python.exe cad/build_enclosure.py [--wipe]
  --wipe  delete the features this script created last time (from cad/.build_state.json) first.
"""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osh  # noqa: E402

DID = "ada0757f8a367ed8c935f14f"
WID = "389f688fe28c85a3add01f94"
EID = "5da49a2f1204f18bc3cad3cc"  # Part Studio 1
STATE = Path(__file__).resolve().parent / ".build_state.json"
MODEL_VERSION = "v2"

# (name, Onshape expression, description). Order matters: derived ones reference earlier ones.
VARIABLES = [
    # --- print / fit
    ("wall", "2 mm", "Base outer wall thickness"),
    ("floor_t", "2 mm", "Base floor thickness"),
    ("lid_t", "2 mm", "Lid thickness"),
    ("fit", "0.3 mm", "Clearance per side: lid hole + cap around the chamber, LCD PCB in its skirt"),
    ("corner_r", "4 mm", "Outer corner radius of base and lid (must be > wall)"),
    # --- lid screws: M3 heat-set inserts in 4 corner posts
    ("post_s", "9 mm", "Corner post size (square); each holds one M3 heat-set insert"),
    ("insert_d", "4.2 mm", "Heat-set insert hole diameter (M3 insert, OD ~4.8 mm measured)"),
    ("insert_depth", "7 mm", "Insert hole depth (insert is 3.8 mm long + room for the screw tip)"),
    ("screw_d", "3.4 mm", "Lid clearance hole for the M3 screws"),
    # --- electronics bay
    ("bb_len", "84 mm", "Breadboard length (X). Half-size ~83, full-size ~165"),
    ("bb_wid", "55 mm", "Breadboard width (Y)"),
    ("bb_gap", "2 mm", "Clearance around the breadboard"),
    ("optics_d", "32 mm", "Depth (Y) of the optics zone in front of the light wall"),
    ("in_h", "40 mm", "Interior height, floor to rim (fits ESP32 on breadboard + LCD under lid)"),
    ("part_t", "1.6 mm", "Light wall thickness (between the optics zone and the USB-C/electronics bay)"),
    ("wire_w", "24 mm", "Wire notch width at the top of the light wall"),
    ("wire_h", "10 mm", "Wire notch depth down from the rim"),
    # --- cuvette + optics (same as v1; better LED/sensor mounting is planned for v3)
    ("cuv_w", "12.5 mm", "Cuvette outer width (standard 12.5 x 12.5)"),
    ("cuv_h", "45 mm", "Cuvette height"),
    ("cuv_fit", "0.35 mm", "Cuvette clearance per side"),
    ("cuv_grab", "10 mm", "How far the cuvette sticks up out of the chamber (to grab it)"),
    ("beam_h", "15 mm", "Light beam height above the cuvette bottom"),
    ("ch_wall", "2.5 mm", "Chamber wall thickness on the sensor sides"),
    ("led_wall", "9 mm", "LED-side wall thickness"),
    ("collar", "4 mm", "Chamber height above the lid (the cap slides over it)"),
    ("led_d", "5.2 mm", "LED hole diameter (sized for 5 mm LEDs; real LEDs are 3 mm -> v3)"),
    ("led_pitch", "6.5 mm", "LED 2x2 grid spacing (R, G, Y, IR)"),
    ("win", "8 mm", "Sensor window size (square), TCS34725 / TSL2591"),
    # --- cuvette cap
    ("cap_wall", "3 mm", "Cap wall and top thickness"),
    ("cap_r", "5 mm", "Cap corner radius seen from above (must be > cap_top_r)"),
    ("cap_top_r", "3 mm", "Cap top-edge roundover (keep <= cap_wall)"),
    ("knob_d", "12 mm", "Cap knob diameter"),
    ("knob_h", "7 mm", "Cap knob height"),
    ("knob_r", "2 mm", "Knob top and base roundover"),
    # --- USB-C
    ("usb_w", "13 mm", "USB-C cutout width (fits the cable's plug housing)"),
    ("usb_h", "8 mm", "USB-C cutout height"),
    ("usb_z", "14 mm", "USB-C cutout centre height above the floor (ESP32 on breadboard)"),
    # --- LCD: HiLetgo HD44780 1602. Defaults = standard 1602 drawing (GDM1602K); measure yours.
    ("lcd_bw", "71.3 mm", "LCD bezel (metal frame) width X - measure"),
    ("lcd_bh", "26.3 mm", "LCD bezel height Y - measure"),
    ("lcd_fit", "0.25 mm", "Window clearance per side around the bezel (snug = light-tight)"),
    ("lcd_bz_t", "7 mm", "Bezel top above the LCD PCB top surface - measure"),
    ("lcd_pcb_w", "80 mm", "LCD PCB width X"),
    ("lcd_pcb_h", "36 mm", "LCD PCB height Y"),
    ("lcd_pcb_t", "1.6 mm", "LCD PCB thickness"),
    ("lcd_dx", "75 mm", "LCD mounting hole spacing X"),
    ("lcd_dy", "31 mm", "LCD mounting hole spacing Y"),
    ("lcd_hole", "2.8 mm", "LCD screw holes in the lid (M2.5; the PCB holes are 2.5 mm)"),
    ("seal_t", "1.6 mm", "LCD light-seal skirt wall thickness"),
    ("seal_lip", "1 mm", "Width of the ledge the LCD PCB is pulled up against"),
    # --- derived (edit the inputs above instead)
    ("box_l", "#bb_len + 2 * #bb_gap + 2 * #wall", "(derived) Outer length X"),
    (
        "box_w",
        "#optics_d + #part_t + #bb_wid + #bb_gap + #post_s + 2 * #wall",
        "(derived) Outer width Y (back corner posts sit behind the breadboard)",
    ),
    ("base_h", "#floor_t + #in_h", "(derived) Base height"),
    ("bb_cy", "#wall + #optics_d + #part_t + #bb_wid / 2", "(derived) Breadboard centre Y (USB-C lines up on it)"),
    ("post_c", "#wall + #post_s / 2", "(derived) Insert/screw centre distance from the outer edges"),
    ("cuv_cx", "#box_l / 2", "Cuvette centre X (default: centred)"),
    ("cuv_cy", "#wall + #optics_d / 2", "Cuvette centre Y (default: middle of optics zone)"),
    ("cuv_hole", "#cuv_w + 2 * #cuv_fit", "(derived) Cuvette hole size"),
    ("ch_h", "#in_h + #lid_t + #collar", "(derived) Chamber height above floor"),
    ("ch_x0", "#cuv_cx - #cuv_hole / 2 - #led_wall", "(derived) Chamber min X (LED face)"),
    ("ch_x1", "#cuv_cx + #cuv_hole / 2 + #ch_wall", "(derived) Chamber max X (180 deg sensor face)"),
    ("ch_y0", "#cuv_cy - #cuv_hole / 2 - #ch_wall", "(derived) Chamber min Y"),
    ("ch_y1", "#cuv_cy + #cuv_hole / 2 + #ch_wall", "(derived) Chamber max Y (90 deg sensor face)"),
    ("pocket", "#cuv_h - #cuv_grab", "(derived) Cuvette pocket depth"),
    ("beam_z", "#floor_t + #ch_h - #pocket + #beam_h", "(derived) Beam height from the bottom of the base"),
    ("cap_h", "#collar + #cuv_grab + 1 mm + #cap_wall", "(derived) Cap height above the lid (without knob)"),
    ("lcd_cy", "#bb_cy", "LCD centre Y (default: over the breadboard)"),
    ("lcd_drop", "#lcd_bz_t - #lid_t", "(derived) LCD PCB top below the lid underside (bezel flush with lid top)"),
]


# ---------------------------------------------------------------- FeatureScript edge queries
def vertical_edges_fs(fid):
    """Straight vertical edges created by feature fid."""
    return (
        "function(context is Context, queries is map) { var out = []; "
        f'for (var e in evaluateQuery(context, qGeometry(qCreatedBy(makeId("{fid}"), EntityType.EDGE), GeometryType.LINE))) {{ '
        'if (abs(evLine(context, {"edge": e}).direction[2]) > 0.999) out = append(out, e); } '
        "return transientQueriesToStrings(out); }"
    )


def top_edges_fs(fid):
    """All edges lying in the top plane of the body created by feature fid."""
    return (
        "function(context is Context, queries is map) { "
        f'var body = qCreatedBy(makeId("{fid}"), EntityType.BODY); '
        'var zt = evBox3d(context, {"topology": body, "tight": true}).maxCorner[2]; var out = []; '
        "for (var e in evaluateQuery(context, qOwnedByBody(body, EntityType.EDGE))) { "
        'var b = evBox3d(context, {"topology": e, "tight": true}); '
        "if (abs(b.minCorner[2] - zt) < 0.0001 * millimeter && abs(b.maxCorner[2] - zt) < 0.0001 * millimeter) "
        "out = append(out, e); } "
        "return transientQueriesToStrings(out); }"
    )


def circle_edges_fs(fid):
    """Circular edges created by feature fid (e.g. the top and base edges of an extruded knob)."""
    return (
        "function(context is Context, queries is map) { return transientQueriesToStrings(evaluateQuery(context, "
        f'qGeometry(qCreatedBy(makeId("{fid}"), EntityType.EDGE), GeometryType.CIRCLE))); '
        "}"
    )


async def name_parts(S, names):
    """names: {partId: name}. Part IDs are the bodies' deterministic IDs."""
    base = f"/api/metadata/d/{DID}/w/{WID}/e/{EID}/p"
    for item in (await S.c.get(base))["items"]:
        pid = item["partId"]
        if pid in names:
            prop = next(p for p in item["properties"] if p["name"] == "Name")
            await S.c.post(
                f"{base}/{quote(pid, safe='')}", data={"properties": [{"propertyId": prop["propertyId"], "value": names[pid]}]}
            )


async def main():
    S = osh.Studio(DID, WID, EID)
    created = []

    if "--wipe" in sys.argv and STATE.exists():
        old = json.loads(STATE.read_text())["features"]
        for fid in reversed(old):
            await S.c.delete(S.path + f"/features/featureid/{fid}")
        print(f"wiped {len(old)} features from the previous build")
        STATE.unlink()

    existing = (await S.features())["features"]
    if existing:
        raise SystemExit(f"Part Studio already has {len(existing)} features; use --wipe (only removes ones this script made).")

    async def add(feature):
        fid = await S.add(feature)
        created.append(fid)
        STATE.write_text(json.dumps({"version": MODEL_VERSION, "features": created}, indent=1))
        return fid

    V = osh.Vars()
    origin = (await S.ids('qCreatedBy(makeId("Origin"), EntityType.VERTEX)'))[0]

    def sketch(name, plane_id):
        return osh.Sketch(name, plane_id, V, origin)

    async def plane(name, ref, expr, flip=False):
        fid = await add(osh.offset_plane(name, ref, expr, flip))
        return (await S.created(fid, "FACE"))[0]

    # ---------------------------------------------------------------- variables
    for name, expr, desc in VARIABLES:
        V.v[name] = V.ev(expr)
        await add(osh.variable(name, expr, desc))
    print("variables:", {k: round(v, 2) for k, v in V.v.items()})

    TOP, RIGHT, FRONT = osh.PLANES["Top"], osh.PLANES["Right"], osh.PLANES["Front"]
    corners = [(x, y) for x in ("#post_c", "#box_l - #post_c") for y in ("#post_c", "#box_w - #post_c")]

    # ---------------------------------------------------------------- base shell
    s = await add(sketch("Base outline", TOP).rect("0 mm", "0 mm", "#box_l", "#box_w").feature())
    base_ext = await add(osh.extrude("Base", s, "#base_h"))
    base = await S.created(base_ext)
    await add(osh.fillet("Base corners", await S.fs(vertical_edges_fs(base_ext)), "#corner_r"))

    rim = await plane("Rim plane", TOP, "#base_h")
    s = await add(sketch("Cavity", rim).rect("#wall", "#wall", "#box_l - 2 * #wall", "#box_w - 2 * #wall").feature())
    cav = await add(osh.extrude("Cavity", s, "#in_h", op="REMOVE", flip=True, scope_ids=base))
    await add(osh.fillet("Cavity corners", await S.fs(vertical_edges_fs(cav)), "#corner_r - #wall"))
    floor_pl = await plane("Floor plane", TOP, "#floor_t")

    # Corner posts with M3 heat-set insert holes (lid screws)
    sk = sketch("Corner posts", floor_pl)
    for x in ("#wall", "#box_l - #wall - #post_s"):
        for y in ("#wall", "#box_w - #wall - #post_s"):
            sk.rect(x, y, "#post_s", "#post_s")
    s = await add(sk.feature())
    await add(osh.extrude("Corner posts", s, "#in_h", op="ADD", scope_ids=base))
    sk = sketch("Insert holes (M3)", rim)
    for x, y in corners:
        sk.circle(x, y, "#insert_d")
    s = await add(sk.feature())
    await add(osh.extrude("Insert holes", s, "#insert_depth", op="REMOVE", flip=True, scope_ids=base))

    # Light wall between the optics zone and the electronics bay, with a wire notch at the top
    s = await add(
        sketch("Light wall", floor_pl).rect("#wall", "#wall + #optics_d", "#box_l - 2 * #wall", "#part_t").feature()
    )
    await add(osh.extrude("Light wall", s, "#in_h", op="ADD", scope_ids=base))
    s = await add(
        sketch("Wire notch", rim)
        .rect_c("#cuv_cx", "#wall + #optics_d + #part_t / 2", "#wire_w", "#part_t + 2 mm")
        .feature()
    )
    await add(osh.extrude("Wire notch", s, "#wire_h", op="REMOVE", flip=True, scope_ids=base))

    # ---------------------------------------------------------------- cuvette chamber
    s = await add(sketch("Chamber", floor_pl).rect("#ch_x0", "#ch_y0", "#ch_x1 - #ch_x0", "#ch_y1 - #ch_y0").feature())
    await add(osh.extrude("Chamber", s, "#ch_h", op="ADD", scope_ids=base))

    top_pl = await plane("Chamber top plane", TOP, "#floor_t + #ch_h")
    s = await add(sketch("Cuvette pocket", top_pl).rect_c("#cuv_cx", "#cuv_cy", "#cuv_hole", "#cuv_hole").feature())
    await add(osh.extrude("Cuvette pocket", s, "#pocket", op="REMOVE", flip=True, scope_ids=base))

    # LED holes: 2x2 grid on the -X face (sketch on a Right-offset plane: sketch x = Y, sketch y = Z)
    led_pl = await plane("LED plane", RIGHT, "#ch_x0")
    sk = sketch("LED holes (R G Y IR)", led_pl)
    for dy in ("-", "+"):
        for dz in ("-", "+"):
            sk.circle(f"#cuv_cy {dy} #led_pitch / 2", f"#beam_z {dz} #led_pitch / 2", "#led_d")
    s = await add(sk.feature())
    await add(osh.extrude("LED holes", s, "#led_wall + 1 mm", op="REMOVE", scope_ids=base))

    # Sensor window opposite the LEDs (+X face) - transmission
    pl = await plane("Sensor plane 180", RIGHT, "#cuv_cx + #cuv_hole / 2")
    s = await add(sketch("Sensor window 180", pl).rect_c("#cuv_cy", "#beam_z", "#win", "#win").feature())
    await add(osh.extrude("Sensor window 180", s, "#ch_wall + 1 mm", op="REMOVE", scope_ids=base))

    # Sensor window at 90 deg (+Y face) - side scatter. Front plane normal is -Y, so flip to go +Y.
    pl = await plane("Sensor plane 90", FRONT, "#cuv_cy + #cuv_hole / 2", flip=True)
    s = await add(sketch("Sensor window 90", pl).rect_c("#cuv_cx", "#beam_z", "#win", "#win").feature())
    await add(osh.extrude("Sensor window 90", s, "#ch_wall + 1 mm", op="REMOVE", flip=True, scope_ids=base))

    # USB-C cutout in the left (-X) wall, lined up with the breadboard centre
    s = await add(sketch("USB-C cutout", RIGHT).rect_c("#bb_cy", "#floor_t + #usb_z", "#usb_w", "#usb_h").feature())
    await add(osh.extrude("USB-C cutout", s, "#wall + 1 mm", op="REMOVE", scope_ids=base))

    # ---------------------------------------------------------------- lid
    s = await add(sketch("Lid outline", rim).rect("0 mm", "0 mm", "#box_l", "#box_w").feature())
    lid_ext = await add(osh.extrude("Lid", s, "#lid_t"))
    lid = await S.created(lid_ext)
    await add(osh.fillet("Lid corners", await S.fs(vertical_edges_fs(lid_ext)), "#corner_r"))

    # LCD light seal under the lid: a skirt around the LCD PCB plus a ledge the PCB is screwed up
    # against, so the only way in past the LCD is the snug bezel window (blocked by the bezel itself).
    seal_w, seal_h = "#lcd_pcb_w + 2 * (#fit + #seal_t)", "#lcd_pcb_h + 2 * (#fit + #seal_t)"
    sk = sketch("LCD seal ledge", rim)
    sk.rect_c("#box_l / 2", "#lcd_cy", seal_w, seal_h)
    sk.rect_c("#box_l / 2", "#lcd_cy", "#lcd_pcb_w - 2 * #seal_lip", "#lcd_pcb_h - 2 * #seal_lip")
    s = await add(sk.feature())
    await add(osh.extrude("LCD seal ledge", s, "#lcd_drop", op="ADD", flip=True, scope_ids=lid))
    sk = sketch("LCD seal skirt", rim)
    sk.rect_c("#box_l / 2", "#lcd_cy", seal_w, seal_h)
    sk.rect_c("#box_l / 2", "#lcd_cy", "#lcd_pcb_w + 2 * #fit", "#lcd_pcb_h + 2 * #fit")
    s = await add(sk.feature())
    await add(osh.extrude("LCD seal skirt", s, "#lcd_drop + #lcd_pcb_t", op="ADD", flip=True, scope_ids=lid))

    sk = sketch("Lid cutouts (chamber, LCD, screws)", rim)
    sk.rect("#ch_x0 - #fit", "#ch_y0 - #fit", "#ch_x1 - #ch_x0 + 2 * #fit", "#ch_y1 - #ch_y0 + 2 * #fit")
    sk.rect_c("#box_l / 2", "#lcd_cy", "#lcd_bw + 2 * #lcd_fit", "#lcd_bh + 2 * #lcd_fit")
    for sx in ("-", "+"):
        for sy in ("-", "+"):
            sk.circle(f"#box_l / 2 {sx} #lcd_dx / 2", f"#lcd_cy {sy} #lcd_dy / 2", "#lcd_hole")
    for x, y in corners:
        sk.circle(x, y, "#screw_d")
    s = await add(sk.feature())
    await add(osh.extrude("Lid cutouts", s, "#lid_t + 1 mm", op="REMOVE", scope_ids=lid))

    # ---------------------------------------------------------------- cuvette cap (rounded, with knob)
    lid_top = await plane("Lid top plane", TOP, "#base_h + #lid_t")
    s = await add(
        sketch("Cap outline", lid_top)
        .rect(
            "#ch_x0 - #fit - #cap_wall",
            "#ch_y0 - #fit - #cap_wall",
            "#ch_x1 - #ch_x0 + 2 * (#fit + #cap_wall)",
            "#ch_y1 - #ch_y0 + 2 * (#fit + #cap_wall)",
        )
        .feature()
    )
    cap_ext = await add(osh.extrude("Cuvette cap", s, "#cap_h"))
    cap = await S.created(cap_ext)
    await add(osh.fillet("Cap corners", await S.fs(vertical_edges_fs(cap_ext)), "#cap_r"))
    top_edges = await S.fs(top_edges_fs(cap_ext))
    if len(top_edges) != 8:
        raise RuntimeError(f"expected 8 cap top edges, got {top_edges}")
    await add(osh.fillet("Cap top roundover", top_edges, "#cap_top_r"))
    s = await add(
        sketch("Cap cavity", lid_top)
        .rect("#ch_x0 - #fit", "#ch_y0 - #fit", "#ch_x1 - #ch_x0 + 2 * #fit", "#ch_y1 - #ch_y0 + 2 * #fit")
        .feature()
    )
    await add(osh.extrude("Cap cavity", s, "#cap_h - #cap_wall", op="REMOVE", scope_ids=cap))

    cap_top = await plane("Cap top plane", TOP, "#base_h + #lid_t + #cap_h")
    s = await add(sketch("Knob", cap_top).circle("(#ch_x0 + #ch_x1) / 2", "(#ch_y0 + #ch_y1) / 2", "#knob_d").feature())
    knob_ext = await add(osh.extrude("Knob", s, "#knob_h", op="ADD", scope_ids=cap))
    knob_edges = await S.fs(circle_edges_fs(knob_ext))
    if len(knob_edges) != 2:
        raise RuntimeError(f"expected 2 knob edges (top + base), got {knob_edges}")
    await add(osh.fillet("Knob roundover", knob_edges, "#knob_r"))

    await name_parts(S, {base[0]: "Base", lid[0]: "Lid", cap[0]: "Cuvette cap"})
    print(f"built {MODEL_VERSION}: {len(created)} features; parts: base={base} lid={lid} cap={cap}")
    for label, fid in (("Base", base_ext), ("Lid", lid_ext), ("Cuvette cap", cap_ext)):
        q = f'qCreatedBy(makeId("{fid}"), EntityType.BODY)'
        print(f"  {label:12s} bbox mm:", [round(x, 2) for x in await S.box(q)])


if __name__ == "__main__":
    asyncio.run(main())
