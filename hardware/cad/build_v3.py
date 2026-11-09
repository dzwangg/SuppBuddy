"""Build the V3 enclosure as an ordinary Onshape feature tree (variables, sketches, extrudes, fillets) in
a new Part Studio, "DeviceHolder V3". It reproduces the geometry of the old one-feature FeatureScript
model (cad/build_fs.py) exactly, but people can edit it the normal Onshape way.

Dimensions come from GROUPS in build_fs.py. The ones in VARS become Part Studio variables (#name, edit
them in the Variable table); every other dimension is written into the sketch/extrude expressions as
a number. Sketches are fully dimensioned from the origin.

API thrift: one call per feature (about 77), no FeatureScript-eval calls. Planes, boolean scopes and
fillet edges are selected with query strings (qCreatedBy / qNonCapEntity / qCapEntity) instead of
looked-up IDs.

Usage:  onshape-mcp/.venv/Scripts/python.exe cad/build_v3.py          create the studio and build
        onshape-mcp/.venv/Scripts/python.exe cad/build_v3.py --dry    print the feature list only
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import osh  # noqa: E402
from build_fs import DID, GROUPS, WID  # noqa: E402

STATE = Path(__file__).resolve().parent / ".v3_state.json"
NAME = "DeviceHolder V3"
TOP, RIGHT, FRONT, ORIGIN = "JDC", "JEC", "JCC", "IB"

DEFAULTS = {pid: dflt for _, ps in GROUPS for pid, _, dflt, _, _ in ps}
LABELS = {pid: label for _, ps in GROUPS for pid, label, _, _, _ in ps}
VARS = ["wall", "floor_t", "lid_t", "fit", "corner_r", "vial_d", "vial_fit", "vcap_d", "vcap_h", "vcap_fit",
        "beam_h", "led_d", "led_depth", "led_pitch", "slit_w", "win", "tsl_sz", "tcs_sz", "usb_z"]

V = osh.Vars()
V.v.update(DEFAULTS)


def num(v):
    return f"{round(v, 6):.10g} mm"


def p(name):
    return f"#{name}" if name in VARS else num(DEFAULTS[name])


def X(s):
    """Expression: a plain number if it uses no variable, otherwise parenthesised."""
    return f"({s})" if "#" in s else num(V.ev(s))


def Q(pid, qs):
    return {"btType": "BTMParameterQueryList-148", "parameterId": pid,
            "queries": [{"btType": "BTMIndividualQuery-138", "queryString": f"query = {qs};", "deterministicIds": []}]}


def body(fid):
    return f'qCreatedBy(id + "{fid}", EntityType.BODY)'


# ---------------------------------------------------------------- derived dimensions (expressions)
bore = X(f"{p('vial_d')} + 2 * {p('vial_fit')}")
pk_depth = X(f"{p('pk_s')} + {p('pk_t')} + {p('pk_back')}")
optics_d = X(f"{p('front_gap')} + {bore} + 2 * {p('ch_wall')} + {pk_depth} + {p('tcs_room')}")
box_l = X(f"{p('bb_len')} + 2 * {p('bb_gap')} + 2 * {p('wall')}")
box_w = X(f"{optics_d} + {p('part_t')} + {p('bb_wid')} + {p('bb_gap')} + {p('post_s')} + 2 * {p('wall')}")
base_h = X(f"{p('floor_t')} + {p('in_h')}")
in_h = p("in_h")
bb_cy = X(f"{p('wall')} + {optics_d} + {p('part_t')} + {p('bb_wid')} / 2")
vial_cx = X(f"{box_l} / 2 + {p('vial_dx')}")
vial_cy = X(f"{p('wall')} + {p('front_gap')} + {p('ch_wall')} + {bore} / 2")
ch_x0 = X(f"{vial_cx} - {bore} / 2 - {p('led_wall')}")
ch_x1 = X(f"{vial_cx} + {bore} / 2 + {p('ch_wall')}")
ch_y0 = X(f"{vial_cy} - {bore} / 2 - {p('ch_wall')}")
ch_y1 = X(f"{vial_cy} + {bore} / 2 + {p('ch_wall')}")
vial_z0 = X(f"{p('floor_t')} + {p('vial_z')}")
beam_z = X(f"{vial_z0} + {p('beam_h')}")
collar_d = X(f"{bore} + 2 * {p('ch_wall')}")
collar_top = X(f"{vial_z0} + {p('vial_h')} - {p('vcap_h')} - 1 mm")
sk_z = X(f"{base_h} + {p('lid_t')} + {p('sk_gap')}")
sl_top_z = X(f"{vial_z0} + {p('vial_h')} + {p('sl_top')}")
sl_d = X(f"{collar_d} + 2 * ({p('fit')} + {p('sl_wall')})")
tsl_z0 = X(f"{beam_z} - {p('tsl_sz')}")
tcs_z0 = X(f"{beam_z} - {p('tcs_sz')}")
tsl_yc = X(f"{vial_cy} - {p('tsl_su')}")
tcs_xc = X(f"{vial_cx} - {p('tcs_su')}")
tsl_bw = X(f"{p('tsl_w')} + 2 * ({p('pk_cl')} + {p('pk_side')})")
tcs_bw = X(f"{p('tcs_w')} + 2 * ({p('pk_cl')} + {p('pk_side')})")
lcd_cx = X(f"{box_l} / 2")
lcd_cy = X(f"{bb_cy} + {p('lcd_off')}")
lcd_drop = X(f"{p('lcd_bz_t')} - {p('lid_t')}")
seal_w = X(f"{p('lcd_pcb_w')} + 2 * ({p('fit')} + {p('seal_t')})")
seal_h = X(f"{p('lcd_pcb_h')} + 2 * ({p('fit')} + {p('seal_t')})")
corners = [(x, y) for x in (X(f"{p('wall')} + {p('post_s')} / 2"), X(f"{box_l} - {p('wall')} - {p('post_s')} / 2"))
           for y in (X(f"{p('wall')} + {p('post_s')} / 2"), X(f"{box_w} - {p('wall')} - {p('post_s')} / 2"))]


def sub(a, b):
    return X(f"{a} - ({b})")


# ---------------------------------------------------------------- feature list
FEATS = []  # (key, builder(fids) -> feature json)


def add(key, fn):
    FEATS.append((key, fn))


def plane(key, name, ref, offset, flip=False):
    add(key, lambda f: osh.offset_plane(name, ref, offset, flip))


def sketch(key, name, plane_key, shapes):
    """shapes(sk) draws on an osh.Sketch. plane_key is a default plane id or the key of a plane feature."""
    def fn(f):
        sk = osh.Sketch(name, TOP, V, ORIGIN)
        shapes(sk)
        feat = sk.feature()
        if plane_key in (TOP, RIGHT, FRONT):
            feat["parameters"] = [osh.P_ids("sketchPlane", [plane_key])]
        else:
            feat["parameters"] = [Q("sketchPlane", f'qCreatedBy(id + "{f[plane_key]}", EntityType.FACE)')]
        return feat
    add(key, fn)


def extrude(key, name, sk_key, depth, op="NEW", flip=False, scope=None):
    def fn(f):
        feat = osh.extrude(name, f[sk_key], depth, op=op, flip=flip)
        if scope:
            feat["parameters"] += [osh.P_bool("defaultScope", False), Q("booleanScope", body(f[scope]))]
        return feat
    add(key, fn)


def fillet(key, name, qs_fn, radius):
    add(key, lambda f: {"btType": "BTMFeature-134", "featureType": "fillet", "name": name,
                        "parameters": [Q("entities", qs_fn(f)), osh.P_qty("radius", radius)]})


def rect(sk, x0, y0, x1, y1):
    sk.rect(x0, y0, sub(x1, x0), sub(y1, y0))


for n in VARS:
    add(f"var_{n}", lambda f, n=n: osh.variable(n, num(DEFAULTS[n]), LABELS[n]))

# ======================== Base
sketch("s_base", "Base outline", TOP, lambda s: s.rect("0 mm", "0 mm", box_l, box_w))
extrude("base", "Base", "s_base", base_h)
fillet("f_base", "Base corners", lambda f: f'qNonCapEntity(id + "{f["base"]}", EntityType.EDGE)', p("corner_r"))
plane("rim", "Rim plane", TOP, base_h)
sketch("s_cav", "Cavity", "rim", lambda s: s.rect(p("wall"), p("wall"), X(f"{box_l} - 2 * {p('wall')}"),
                                                 X(f"{box_w} - 2 * {p('wall')}")))
extrude("cav", "Cavity", "s_cav", in_h, op="REMOVE", flip=True, scope="base")
plane("floor", "Floor plane", TOP, p("floor_t"))


def _posts(s):
    for x in (p("wall"), X(f"{box_l} - {p('wall')} - {p('post_s')}")):
        for y in (p("wall"), X(f"{box_w} - {p('wall')} - {p('post_s')}")):
            s.rect(x, y, p("post_s"), p("post_s"))
    s.rect(p("wall"), X(f"{p('wall')} + {optics_d}"), X(f"{box_l} - 2 * {p('wall')}"), p("part_t"))
    rect(s, ch_x0, ch_y0, ch_x1, ch_y1)


sketch("s_posts", "Corner posts, light wall, optics block", "floor", _posts)
extrude("posts", "Corner posts, light wall, optics block", "s_posts", in_h, op="ADD", scope="base")
sketch("s_collar", "Collar", "rim", lambda s: s.circle(vial_cx, vial_cy, collar_d))
extrude("collar", "Collar", "s_collar", sub(collar_top, base_h), op="ADD", scope="base")
tsl_top = X(f"{tsl_z0} + {p('tsl_h')} - {p('pk_hz')}")
tcs_top = X(f"{tcs_z0} + {p('tcs_h')} - {p('pk_hz')}")
sketch("s_tslp", "TSL2591 pocket (180 deg)", "floor",
       lambda s: s.rect(ch_x1, X(f"{tsl_yc} - {tsl_bw} / 2"), pk_depth, tsl_bw))
extrude("tslp", "TSL2591 pocket (180 deg)", "s_tslp", sub(tsl_top, p("floor_t")), op="ADD", scope="base")
sketch("s_tcsp", "TCS34725 pocket (90 deg)", "floor",
       lambda s: s.rect(X(f"{tcs_xc} - {tcs_bw} / 2"), ch_y1, tcs_bw, pk_depth))
extrude("tcsp", "TCS34725 pocket (90 deg)", "s_tcsp", sub(tcs_top, p("floor_t")), op="ADD", scope="base")


def _inserts(s):
    for x, y in corners:
        s.circle(x, y, p("insert_d"))


sketch("s_ins", "Insert holes (M3)", "rim", _inserts)
extrude("ins", "Insert holes (M3)", "s_ins", p("insert_depth"), op="REMOVE", flip=True, scope="base")
sketch("s_wire", "Wire notch", "rim",
       lambda s: s.rect(X(f"{vial_cx} - {p('wire_w')} / 2"), X(f"{p('wall')} + {optics_d} - 1 mm"),
                        p("wire_w"), X(f"{p('part_t')} + 2 mm")))
extrude("wire", "Wire notch", "s_wire", p("wire_h"), op="REMOVE", flip=True, scope="base")
sketch("s_bore", "Vial bore", "floor", lambda s: s.circle(vial_cx, vial_cy, bore))
extrude("bore", "Vial bore", "s_bore", X(f"{collar_top} + 1 mm - {vial_z0}"), op="REMOVE", scope="base")

# LEDs: one vertical column on the -X face, in the plane through the vial axis (sketch x = Y, y = Z)
plane("ledpl", "LED plane", RIGHT, ch_x0)


def _leds(s):
    for k in ("- 1.5", "- 0.5", "+ 0.5", "+ 1.5"):
        s.circle(vial_cy, X(f"{beam_z} {k} * {p('led_pitch')}"), p("led_d"))


sketch("s_led", "LED holes (R G Y IR)", "ledpl", _leds)
extrude("led", "LED holes", "s_led", p("led_depth"), op="REMOVE", scope="base")
slit_h = X(f"3 * {p('led_pitch')} + {p('led_d')}")
plane("slitpl", "Slit plane", RIGHT, X(f"{ch_x0} + {p('led_depth')}"))
sketch("s_slit", "Slit aperture", "slitpl", lambda s: s.rect_c(vial_cy, beam_z, p("slit_w"), slit_h))
extrude("slit", "Slit aperture", "s_slit", X(f"{p('led_wall')} - {p('led_depth')} + 1 mm"), op="REMOVE", scope="base")
w180 = X(f"{vial_cx} + {bore} / 2 - 2 mm")
plane("w180pl", "Window 180 plane", RIGHT, w180)
sketch("s_w180", "Sensor window 180", "w180pl", lambda s: s.rect_c(vial_cy, beam_z, p("win"), p("win")))
extrude("w180", "Sensor window 180", "s_w180", X(f"{ch_x1} + 1 mm - {w180}"), op="REMOVE", scope="base")
w90 = X(f"{vial_cy} + {bore} / 2 - 2 mm")
plane("w90pl", "Window 90 plane", FRONT, w90, flip=True)
sketch("s_w90", "Sensor window 90", "w90pl", lambda s: s.rect_c(vial_cx, beam_z, p("win"), p("win")))
extrude("w90", "Sensor window 90", "s_w90", X(f"{ch_y1} + 1 mm - {w90}"), op="REMOVE", flip=True, scope="base")

# Slide-in sensor pockets: board slot + parts clearance in front + open back, all from the board's bottom edge up
plane("tslpl", "TSL2591 slot plane", TOP, tsl_z0)


def _tsl(s):
    tin = X(f"{p('tsl_w')} / 2 - {p('pk_lip')}")
    rect(s, X(f"{ch_x1} + {p('pk_s')}"), X(f"{tsl_yc} - {p('tsl_w')} / 2 - {p('pk_cl')}"),
         X(f"{ch_x1} + {p('pk_s')} + {p('pk_t')}"), X(f"{tsl_yc} + {p('tsl_w')} / 2 + {p('pk_cl')}"))
    rect(s, ch_x1, X(f"{tsl_yc} - {tin}"), X(f"{ch_x1} + {p('pk_s')} + 0.1 mm"), X(f"{tsl_yc} + {tin}"))
    rect(s, X(f"{ch_x1} + {p('pk_s')} + {p('pk_t')} - 0.1 mm"), X(f"{tsl_yc} - {tin}"),
         X(f"{ch_x1} + {pk_depth} + 1 mm"), X(f"{tsl_yc} + {tin}"))


sketch("s_tsl", "TSL2591 slot", "tslpl", _tsl)
extrude("tsl", "TSL2591 slot", "s_tsl", X(f"{p('tsl_h')} - {p('pk_hz')} + 1 mm"), op="REMOVE", scope="base")
plane("tcspl", "TCS34725 slot plane", TOP, tcs_z0)


def _tcs(s):
    tin = X(f"{p('tcs_w')} / 2 - {p('pk_lip')}")
    rect(s, X(f"{tcs_xc} - {p('tcs_w')} / 2 - {p('pk_cl')}"), X(f"{ch_y1} + {p('pk_s')}"),
         X(f"{tcs_xc} + {p('tcs_w')} / 2 + {p('pk_cl')}"), X(f"{ch_y1} + {p('pk_s')} + {p('pk_t')}"))
    rect(s, X(f"{tcs_xc} - {tin}"), ch_y1, X(f"{tcs_xc} + {tin}"), X(f"{ch_y1} + {p('pk_s')} + 0.1 mm"))
    rect(s, X(f"{tcs_xc} - {tin}"), X(f"{ch_y1} + {p('pk_s')} + {p('pk_t')} - 0.1 mm"),
         X(f"{tcs_xc} + {tin}"), X(f"{ch_y1} + {pk_depth} + 1 mm"))


sketch("s_tcs", "TCS34725 slot", "tcspl", _tcs)
extrude("tcs", "TCS34725 slot", "s_tcs", X(f"{p('tcs_h')} - {p('pk_hz')} + 1 mm"), op="REMOVE", scope="base")
sketch("s_usb", "USB-C cutout", RIGHT,
       lambda s: s.rect_c(bb_cy, X(f"{p('floor_t')} + {p('usb_z')}"), p("usb_w"), p("usb_h")))
extrude("usb", "USB-C cutout", "s_usb", X(f"{p('wall')} + 1 mm"), op="REMOVE", scope="base")

# ======================== Lid
sketch("s_lid", "Lid outline", "rim", lambda s: s.rect("0 mm", "0 mm", box_l, box_w))
extrude("lid", "Lid", "s_lid", p("lid_t"))
fillet("f_lid", "Lid corners", lambda f: f'qNonCapEntity(id + "{f["lid"]}", EntityType.EDGE)', p("corner_r"))
sketch("s_skirt", "LCD seal skirt", "rim", lambda s: (
    s.rect_c(lcd_cx, lcd_cy, seal_w, seal_h),
    s.rect_c(lcd_cx, lcd_cy, X(f"{p('lcd_pcb_w')} + 2 * {p('fit')}"), X(f"{p('lcd_pcb_h')} + 2 * {p('fit')}"))))
extrude("skirt", "LCD seal skirt", "s_skirt", X(f"{lcd_drop} + {p('lcd_pcb_t')}"), op="ADD", flip=True, scope="lid")
sketch("s_ledge", "LCD seal ledge", "rim", lambda s: (
    s.rect_c(lcd_cx, lcd_cy, seal_w, seal_h),
    s.rect_c(lcd_cx, lcd_cy, X(f"{p('lcd_pcb_w')} - 2 * {p('seal_lip')}"), X(f"{p('lcd_pcb_h')} - 2 * {p('seal_lip')}"))))
extrude("ledge", "LCD seal ledge", "s_ledge", lcd_drop, op="ADD", flip=True, scope="lid")


def _lidcuts(s):
    s.rect_c(lcd_cx, lcd_cy, X(f"{p('lcd_bw')} + 2 * {p('lcd_fit')}"), X(f"{p('lcd_bh')} + 2 * {p('lcd_fit')}"))
    s.circle(vial_cx, vial_cy, X(f"{collar_d} + 2 * {p('fit')}"))
    for sx in ("-", "+"):
        for sy in ("-", "+"):
            s.circle(X(f"{lcd_cx} {sx} {p('lcd_dx')} / 2"), X(f"{lcd_cy} {sy} {p('lcd_dy')} / 2"), p("lcd_hole"))
    for x, y in corners:
        s.circle(x, y, p("screw_d"))


sketch("s_lidcut", "Lid cutouts (LCD window, collar, screws)", "rim", _lidcuts)
extrude("lidcut", "Lid cutouts", "s_lidcut", X(f"{p('lid_t')} + 1 mm"), op="REMOVE", scope="lid")

# ======================== Vial cap sleeve
plane("slpl", "Sleeve bottom plane", TOP, sk_z)
sketch("s_sl", "Sleeve outline", "slpl", lambda s: s.circle(vial_cx, vial_cy, sl_d))
extrude("sl", "Vial cap sleeve", "s_sl", sub(sl_top_z, sk_z))
fillet("f_sl", "Sleeve top roundover", lambda f: f'qCapEntity(id + "{f["sl"]}", CapType.END, EntityType.EDGE)', p("sl_r"))
sketch("s_slsk", "Skirt bore", "slpl", lambda s: s.circle(vial_cx, vial_cy, X(f"{collar_d} + 2 * {p('fit')}")))
extrude("slsk", "Skirt bore", "s_slsk", X(f"{collar_top} + 1 mm - {sk_z}"), op="REMOVE", scope="sl")
sketch("s_slcap", "Cap pocket", "slpl", lambda s: s.circle(vial_cx, vial_cy, X(f"{p('vcap_d')} + {p('vcap_fit')}")))
extrude("slcap", "Cap pocket", "s_slcap", X(f"{vial_z0} + {p('vial_h')} - {sk_z}"), op="REMOVE", scope="sl")


async def main():
    if "--dry" in sys.argv:
        for k, _ in FEATS:
            print(k)
        print(len(FEATS), "features")
        return
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    S = osh.Studio(DID, WID, st.get("element"))
    if not st.get("element"):
        r = await S.post(f"/api/v9/partstudios/d/{DID}/w/{WID}", data={"name": NAME})
        st = {"element": r["id"], "features": {}}
        S.eid = r["id"]
        STATE.write_text(json.dumps(st, indent=1))
        print("created Part Studio", r["id"])
    f = st["features"]
    for key, fn in FEATS:
        if key in f:
            continue
        r = await S.post(S.path + "/features", data={"btType": "BTFeatureDefinitionCall-1406", "feature": fn(f)})
        f[key] = r["feature"]["featureId"]
        STATE.write_text(json.dumps(st, indent=1))
        status = (r.get("featureState") or {}).get("featureStatus")
        if status != "OK":
            raise SystemExit(f"{key} ({f[key]}): {status}. Fix it in Onshape or delete it, then re-run to continue.")
    print(f"built {len(f)} features in {S.eid}")

    # name the parts (creation order: base, lid, sleeve)
    mbase = f"/api/v9/metadata/d/{DID}/w/{WID}/e/{S.eid}/p"
    from urllib.parse import quote
    names = {"Part 1": "Base", "Part 2": "Lid", "Part 3": "Vial cap sleeve"}
    for item in (await S.get(mbase))["items"]:
        prop = next(q for q in item["properties"] if q["name"] == "Name")
        name = names.get(prop.get("value"))
        if name:
            await S.post(f"{mbase}/{quote(item['partId'], safe='')}",
                         data={"properties": [{"propertyId": prop["propertyId"], "value": name}]})
        print(f"  {item['partId']}: {prop.get('value')} -> {name or '(unchanged)'}")


if __name__ == "__main__":
    asyncio.run(main())
