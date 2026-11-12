"""Build V4: DeviceHolder V3 with the two light sensors swapped (asked for on 2026-11-11).

The TCS34725 (the bigger board, 20.4 mm square) moves to the 180 deg pocket opposite the LEDs, where it
reads transmitted light. The TSL2591 (16 x 19 mm) moves to the 90 deg pocket, where it reads scattered
light. That matches the firmware (firmware/SupplementOpticalTester/Config.h). Everything else is V3: the
same variables, box, windows, lid and sleeve. Each board keeps its own height (#tsl_sz, #tcs_sz), so the
slot planes don't move.

Steps (about 12 API calls, no FeatureScript eval):
  1. Copy the DeviceHolder V3 Part Studio (elements/copyelement) and rename the copy "DeviceHolder V4".
  2. Read the copy's feature list and match it to build_v3.FEATS by position, checking names and types.
  3. Redraw the two pocket sketches and the two slot sketches at the swapped positions, and rename the
     two pocket extrudes.
It records what it did in .v4_state.json and resumes from it.

The chip offsets tsl_su and tcs_su (0 by default) now run along +X for the TSL2591 and +Y for the
TCS34725, the other way round from V3.

Usage:  onshape-mcp/.venv/Scripts/python.exe cad/build_v4.py          copy V3 and patch the copy
        onshape-mcp/.venv/Scripts/python.exe cad/build_v4.py --dry    self-test and print the new positions
"""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v3 as v3  # noqa: E402
from build_v3 import DID, WID, X, ch_x1, ch_y1, osh, p, pk_depth, rect, vial_cx, vial_cy  # noqa: E402

STATE = Path(__file__).resolve().parent / ".v4_state.json"
NAME = "DeviceHolder V4"
V3_EID = json.loads(v3.STATE.read_text())["element"]
FEATS = dict(v3.FEATS)  # key -> fn(feature ids) -> feature JSON, exactly as build_v3.py builds V3

# Board centres at their new positions
tsl_xc = X(f"{vial_cx} - {p('tsl_su')}")
tcs_yc = X(f"{vial_cy} - {p('tcs_su')}")


# ---------------------------------------------------------------- the two pocket positions, for any board
def pocket_180(s, bw, yc):
    """Pocket block on the +X face of the optics block, opposite the LEDs (transmitted light)."""
    s.rect(ch_x1, X(f"{yc} - {bw} / 2"), pk_depth, bw)


def pocket_90(s, bw, xc):
    """Pocket block on the +Y face of the optics block, 90 deg to the beam (scattered light)."""
    s.rect(X(f"{xc} - {bw} / 2"), ch_y1, bw, pk_depth)


def slot_180(s, w, yc):
    """Board slot, parts clearance in front of it and open back, for a board w wide at 180 deg."""
    tin = X(f"{w} / 2 - {p('pk_lip')}")
    rect(s, X(f"{ch_x1} + {p('pk_s')}"), X(f"{yc} - {w} / 2 - {p('pk_cl')}"),
         X(f"{ch_x1} + {p('pk_s')} + {p('pk_t')}"), X(f"{yc} + {w} / 2 + {p('pk_cl')}"))
    rect(s, ch_x1, X(f"{yc} - {tin}"), X(f"{ch_x1} + {p('pk_s')} + 0.1 mm"), X(f"{yc} + {tin}"))
    rect(s, X(f"{ch_x1} + {p('pk_s')} + {p('pk_t')} - 0.1 mm"), X(f"{yc} - {tin}"),
         X(f"{ch_x1} + {pk_depth} + 1 mm"), X(f"{yc} + {tin}"))


def slot_90(s, w, xc):
    """The same for a board w wide at 90 deg."""
    tin = X(f"{w} / 2 - {p('pk_lip')}")
    rect(s, X(f"{xc} - {w} / 2 - {p('pk_cl')}"), X(f"{ch_y1} + {p('pk_s')}"),
         X(f"{xc} + {w} / 2 + {p('pk_cl')}"), X(f"{ch_y1} + {p('pk_s')} + {p('pk_t')}"))
    rect(s, X(f"{xc} - {tin}"), ch_y1, X(f"{xc} + {tin}"), X(f"{ch_y1} + {p('pk_s')} + 0.1 mm"))
    rect(s, X(f"{xc} - {tin}"), X(f"{ch_y1} + {p('pk_s')} + {p('pk_t')} - 0.1 mm"),
         X(f"{xc} + {tin}"), X(f"{ch_y1} + {pk_depth} + 1 mm"))


def sketch_feat(name, plane_fid, draw):
    sk = osh.Sketch(name, v3.TOP, v3.V, v3.ORIGIN)
    draw(sk)
    feat = sk.feature()
    feat["parameters"] = [v3.Q("sketchPlane", f'qCreatedBy(id + "{plane_fid}", EntityType.FACE)')]
    return feat


def renamed(key, name):
    return lambda f: dict(FEATS[key](f), name=name)


# ---------------------------------------------------------------- V4 = V3 with these features replaced
PATCH = {
    "s_tslp": lambda f: sketch_feat("TSL2591 pocket (90 deg)", f["floor"],
                                    lambda s: pocket_90(s, v3.tsl_bw, tsl_xc)),
    "tslp": renamed("tslp", "TSL2591 pocket (90 deg)"),
    "s_tcsp": lambda f: sketch_feat("TCS34725 pocket (180 deg)", f["floor"],
                                    lambda s: pocket_180(s, v3.tcs_bw, tcs_yc)),
    "tcsp": renamed("tcsp", "TCS34725 pocket (180 deg)"),
    "s_tsl": lambda f: sketch_feat("TSL2591 slot", f["tslpl"], lambda s: slot_90(s, p("tsl_w"), tsl_xc)),
    "s_tcs": lambda f: sketch_feat("TCS34725 slot", f["tcspl"], lambda s: slot_180(s, p("tcs_w"), tcs_yc)),
}


def selftest():
    """Given V3's layout, the generic shapes above must rebuild V3's four sensor sketches exactly."""
    f = {k: f"<{k}>" for k in FEATS}
    v3_layout = {
        "s_tslp": sketch_feat("TSL2591 pocket (180 deg)", f["floor"], lambda s: pocket_180(s, v3.tsl_bw, v3.tsl_yc)),
        "s_tcsp": sketch_feat("TCS34725 pocket (90 deg)", f["floor"], lambda s: pocket_90(s, v3.tcs_bw, v3.tcs_xc)),
        "s_tsl": sketch_feat("TSL2591 slot", f["tslpl"], lambda s: slot_180(s, p("tsl_w"), v3.tsl_yc)),
        "s_tcs": sketch_feat("TCS34725 slot", f["tcspl"], lambda s: slot_90(s, p("tcs_w"), v3.tcs_xc)),
    }
    for key, feat in v3_layout.items():
        if feat != FEATS[key](f):
            raise SystemExit(f"self-test failed: the generic shape for {key} doesn't reproduce V3")
    print("self-test OK: the generic pocket and slot shapes rebuild V3's sensor sketches exactly")


def positions():
    ev = v3.V.ev
    x1, y1, d = ev(ch_x1), ev(ch_y1), ev(pk_depth)
    tcs_half, tsl_half = ev(v3.tcs_bw) / 2, ev(v3.tsl_bw) / 2
    print(f"TCS34725 at 180 deg: pocket x {x1:.2f}..{x1 + d:.2f}, y {ev(tcs_yc) - tcs_half:.2f}..{ev(tcs_yc) + tcs_half:.2f},"
          f" top z {ev(v3.tcs_top):.2f}")
    print(f"TSL2591  at 90 deg:  pocket x {ev(tsl_xc) - tsl_half:.2f}..{ev(tsl_xc) + tsl_half:.2f}, y {y1:.2f}..{y1 + d:.2f},"
          f" top z {ev(v3.tsl_top):.2f}")


async def main():
    selftest()
    positions()
    if "--dry" in sys.argv:
        return
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    S = osh.Studio(DID, WID, st.get("element"))

    def save():
        STATE.write_text(json.dumps(st, indent=1))

    if not st.get("element"):
        r = await S.post(f"/api/v9/elements/copyelement/{DID}/workspace/{WID}",
                         data={"documentIdSource": DID, "workspaceIdSource": WID, "elementIdSource": V3_EID})
        st = {"element": r["id"]}
        S.eid = r["id"]
        save()
        print(f"copied DeviceHolder V3 to {r['id']} ({r.get('name')!r})")
    if not st.get("renamed"):
        mpath = f"/api/v9/metadata/d/{DID}/w/{WID}/e/{S.eid}"
        prop = next(q for q in (await S.get(mpath))["properties"] if q["name"] == "Name")
        if prop.get("value") != NAME:
            await S.post(mpath, data={"properties": [{"propertyId": prop["propertyId"], "value": NAME}]})
        st["renamed"] = True
        save()
        print(f"renamed the tab {prop.get('value')!r} -> {NAME!r}")
    if "features" not in st:
        feats = (await S.features())["features"]
        dummy = {k: f"<{k}>" for k in FEATS}
        want = [(k, fn(dummy).get("featureType"), fn(dummy)["name"]) for k, fn in v3.FEATS]
        got = [(ft.get("featureType"), ft.get("name")) for ft in feats]
        if got != [w[1:] for w in want]:
            i = next((i for i, (g, w) in enumerate(zip(got, want)) if g != w[1:]), min(len(got), len(want)))
            raise SystemExit(f"the copy's {len(got)} features don't match the {len(want)} in build_v3.FEATS. "
                             f"First difference at #{i}: {got[i] if i < len(got) else None} vs "
                             f"{want[i][1:] if i < len(want) else None}. Was V3 edited by hand?")
        st["features"] = {k: ft["featureId"] for (k, _, _), ft in zip(want, feats)}
        save()
        print(f"matched {len(feats)} features to build_v3.FEATS")
    f = st["features"]
    for key, fn in PATCH.items():
        status = await S.update(f[key], fn(f))
        print(f"  {key:7} {f[key]}: {status}")
        if status != "OK":
            raise SystemExit(f"{key} didn't regenerate. Fix it in Onshape or re-run.")
    r = await S.features()
    bad = {fid: s.get("featureStatus") for fid, s in (r.get("featureStates") or {}).items()
           if s.get("featureStatus") != "OK"}
    print(f"{len(r['features'])} features, " + (f"NOT OK: {bad}" if bad else "all regenerate OK"))

    # the copy keeps the part names; fix them only if it didn't
    mbase = f"/api/v9/metadata/d/{DID}/w/{WID}/e/{S.eid}/p"
    names = {"Part 1": "Base", "Part 2": "Lid", "Part 3": "Vial cap sleeve"}
    for item in (await S.get(mbase))["items"]:
        prop = next(q for q in item["properties"] if q["name"] == "Name")
        name = names.get(prop.get("value"))
        if name:
            await S.post(f"{mbase}/{quote(item['partId'], safe='')}",
                         data={"properties": [{"propertyId": prop["propertyId"], "value": name}]})
        print(f"  part {item['partId']}: {prop.get('value')}" + (f" -> {name}" if name else ""))


if __name__ == "__main__":
    asyncio.run(main())
