"""SuppBuddy V3 product renders with Blender 5.1 / Cycles.

    "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" -b --factory-startup \
        -P cad/render/scene.py -- --shot exploded [--res 3840x2160] [--samples 256]

Shots: hero, exploded, cutaway.  Output: cad/render/out/<shot>.png (RGBA: transparent film with a
shadow catcher, so compose.py can put any background behind it) and <shot>.json (pixel positions
of the label anchors).

The printed parts are the real V3 meshes (cad/render/stl, made by export_stl.py). Everything
else (vial, LEDs, sensor boards, LCD, ESP32, breadboard, fasteners, cable) is modelled here from
the dimensions in details.md and put where build_fs.py puts its hole/pocket at default values.
Model space is mm (X right, Y back, Z up); Blender gets metres.
"""

import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return ARGV[ARGV.index(name) + 1] if name in ARGV else default


SHOT = opt("--shot", "hero")
W, H = (int(v) for v in opt("--res", "3840x2160").split("x"))
SAMPLES = int(opt("--samples", "256"))
OUT = HERE / "out"
MM = 0.001
DUMP = opt("--dump", None)   # line-drawing export: assembled | exploded | cut_y | cut_z

# ---- V3 layout at default parameters (mm) -------------------------------------------------
BASE_H, LID_TOP = 42.0, 44.0
VX, VY, VZ0 = 46.0, 21.6, 2.0               # vial axis, vial bottom (floor top)
VIAL_R, CAP_R, CAP_H = 13.7, 12.35, 10.0     # SKS 20 mL: body 27.4, cap 24.7, 60 tall with cap
FILL = 33.0                                  # liquid height above the vial bottom (fill line)
LED_FACE_X = 22.9                            # -X face of the optics block; LED lips stop here
LEDS = [("blue", 11.0), ("green", 17.0), ("red", 23.0), ("white", 29.0)]  # bottom to top (firmware: W, R, G, B)
BEAM_Z = 20.0
TSL = dict(x0=64.3, x1=65.9, y0=13.6, y1=29.6, z0=10.5, z1=29.5)       # 2 mm slot at x 64.1-66.1
TCS = dict(y0=39.9, y1=41.5, x0=35.85, x1=56.15, z0=9.6, z1=29.9)      # 2 mm slot at y 39.7-41.7
BB = (46.0, 88.0)                                                     # breadboard + LCD centre
POSTS = [(6.5, 6.5), (85.5, 6.5), (6.5, 122.0), (85.5, 122.0)]
LCD_HOLES = [(46 + sx * 37.5, 88 + sy * 15.5) for sx in (-1, 1) for sy in (-1, 1)]
YCUT = 21.62                                 # cutaway plane (through the vial axis)
ZCUT = 18.5                                  # plan-section plane (through an LED hole + both windows)

LED_RGB = {"blue": (0.02, 0.12, 1.0), "green": (0.03, 1.0, 0.12), "red": (1.0, 0.025, 0.012),
           "white": (1.0, 0.92, 0.80)}

SC = bpy.context.scene
OBJ = {}          # name -> object
GROUP = {}        # name -> group tag (for exploded offsets)


# ---- materials ----------------------------------------------------------------------------
def mat(name, color, rough=0.5, metal=0.0, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    keys = {"transmission": "Transmission Weight", "ior": "IOR", "coat": "Coat Weight",
            "coat_rough": "Coat Roughness", "emission": "Emission Color", "strength": "Emission Strength",
            "spec": "Specular IOR Level", "sss": "Subsurface Weight", "sheen": "Sheen Weight"}
    for k, v in kw.items():
        b.inputs[keys[k]].default_value = (*v, 1) if isinstance(v, tuple) else v
    return m


def edge_round(m, radius_mm=0.3, layers=False):
    """Cycles bevel shader (rounded-edge highlights) and optional 0.2 mm FDM layer lines."""
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    bev = nt.nodes.new("ShaderNodeBevel")
    bev.inputs["Radius"].default_value = radius_mm * MM
    bev.samples = 8
    normal = bev.outputs["Normal"]
    if layers:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 2 * math.pi / (0.2 * MM)
        nt.links.new(sep.outputs["Z"], mul.inputs[0])
        sin = nt.nodes.new("ShaderNodeMath")
        sin.operation = "SINE"
        nt.links.new(mul.outputs[0], sin.inputs[0])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = 0.015 * MM
        nt.links.new(sin.outputs[0], bump.inputs["Height"])
        nt.links.new(normal, bump.inputs["Normal"])
        normal = bump.outputs["Normal"]
    nt.links.new(normal, b.inputs["Normal"])
    return m


def liquid_mat():
    m = mat("liquid", (1, 1, 1), rough=0.0, transmission=1.0, ior=1.333)
    nt = m.node_tree
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (1.0, 0.55, 0.08, 1)
    vol.inputs["Density"].default_value = 55.0
    nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def textured(name, image, rough=0.5, emission=0.0):
    m = mat(name, (0.8, 0.8, 0.8), rough=rough)
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(image))
    b = nt.nodes["Principled BSDF"]
    if emission:
        b.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emission
        b.inputs["Roughness"].default_value = 0.2
        b.inputs["Specular IOR Level"].default_value = 0.12
    else:
        nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    return m


def beam_mat(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 0.7
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(pw.outputs[0], mix.inputs["Fac"])
    nt.links.new(em.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def build_materials(theme):
    M = {}
    M["print"] = edge_round(mat("print", (0.030, 0.032, 0.037), rough=0.55, spec=0.45), 0.35, layers=True)
    M["section"] = mat("section", (0.62, 0.68, 0.75) if theme == "dark" else (0.93, 0.42, 0.10), rough=0.6)
    M["glass"] = mat("glass", (1, 1, 1), rough=0.0, transmission=1.0, ior=1.575)
    M["liquid"] = liquid_mat()
    M["cap"] = edge_round(mat("cap", (0.80, 0.80, 0.78), rough=0.42, sss=0.1), 0.2)
    on = 1.0 if SHOT in ("hero", "cutaway") else 0.6
    for k, c in LED_RGB.items():
        tint = c
        M["led_" + k] = mat("led_" + k, tint, rough=0.2, transmission=0.35, ior=1.5, coat=0.6,
                            emission=c, strength=6.0 * on)
    M["pcb_tsl"] = edge_round(mat("pcb_tsl", (0.02, 0.10, 0.30), rough=0.35, coat=0.4), 0.15)
    M["pcb_tcs"] = edge_round(mat("pcb_tcs", (0.01, 0.06, 0.22), rough=0.35, coat=0.4), 0.15)
    M["pcb_lcd"] = edge_round(mat("pcb_lcd", (0.02, 0.16, 0.05), rough=0.35, coat=0.4), 0.15)
    M["pcb_esp"] = edge_round(mat("pcb_esp", (0.012, 0.012, 0.014), rough=0.35, coat=0.4), 0.15)
    M["gold"] = mat("gold", (1.0, 0.74, 0.32), rough=0.22, metal=1.0)
    M["steel"] = edge_round(mat("steel", (0.78, 0.78, 0.80), rough=0.22, metal=1.0), 0.15)
    M["brass"] = mat("brass", (0.88, 0.62, 0.26), rough=0.3, metal=1.0)
    M["black"] = edge_round(mat("black", (0.012, 0.012, 0.013), rough=0.45), 0.15)
    M["chip"] = mat("chip", (0.015, 0.015, 0.017), rough=0.3, coat=0.5)
    M["window"] = mat("window", (0.35, 0.28, 0.08), rough=0.1, coat=1.0)
    M["white_led"] = mat("white_led", (1.0, 0.86, 0.35), rough=0.3)
    M["shield"] = edge_round(mat("shield", (0.80, 0.80, 0.80), rough=0.3, metal=1.0), 0.1)
    M["bb"] = textured("bb", HERE / "tex" / "breadboard.png", rough=0.55)
    M["bb_body"] = mat("bb_body", (0.86, 0.85, 0.80), rough=0.55)
    lcd_png = HERE / "tex" / f"lcd_{SHOT}.png"
    M["lcd"] = textured("lcd", lcd_png if lcd_png.exists() else HERE / "tex" / "lcd_hero.png", emission=3.0)
    M["lcd_frame"] = edge_round(mat("lcd_frame", (0.035, 0.035, 0.04), rough=0.35, metal=0.6), 0.2)
    M["rubber"] = mat("rubber", (0.018, 0.018, 0.02), rough=0.55, sheen=0.3)
    M["usb_metal"] = mat("usb_metal", (0.85, 0.85, 0.87), rough=0.18, metal=1.0)
    for k, c in LED_RGB.items():
        M["beam_" + k] = beam_mat("beam_" + k, c, 14.0)
        M["halo_" + k] = beam_mat("halo_" + k, c, 1.6)
    return M


# ---- mesh builders (all inputs in mm) ------------------------------------------------------
def finish(ob, material, smooth_deg=32, group=None):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5 * MM)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(smooth_deg))
    if material is not None:
        me.materials.append(material)
    OBJ[ob.name] = ob
    GROUP[ob.name] = group
    return ob


def mesh(name, verts, faces, material, group=None, smooth_deg=32):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x * MM, y * MM, z * MM) for x, y, z in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    SC.collection.objects.link(ob)
    return finish(ob, material, smooth_deg, group)


def box(name, p0, p1, material, group=None, bevel=0.0):
    (x0, y0, z0), (x1, y1, z1) = p0, p1
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = mesh(name, v, f, material, group)
    if bevel and not DUMP:
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width = bevel * MM
        mod.segments = 3
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
    return ob


def revolve(name, prof, material, center, axis="Z", segs=128, rib=None, closed=False, group=None,
            smooth_deg=32):
    """Revolve a (radius, height) profile about an axis through `center`. Points with r == 0 are
    on the axis. Flagged points (r, h, True) get rib(theta) added to their radius."""
    verts, rings = [], []
    for p in prof:
        r, h = p[0], p[1]
        if r <= 1e-9:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, h))
            continue
        ring = []
        for i in range(segs):
            t = 2 * math.pi * i / segs
            rr = r + (rib(t) if rib and len(p) > 2 and p[2] else 0.0)
            ring.append(len(verts))
            verts.append((rr * math.cos(t), rr * math.sin(t), h))
        rings.append(ring)
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    faces = []
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1:
            continue
        for i in range(segs):
            j = (i + 1) % segs
            if len(a) == 1:
                faces.append((a[0], b[i], b[j]))
            elif len(b) == 1:
                faces.append((a[i], a[j], b[0]))
            else:
                faces.append((a[i], a[j], b[j], b[i]))
    cx, cy, cz = center
    sign = -1.0 if axis.startswith("-") else 1.0
    ax = axis[-1]
    out = []
    for x, y, h in verts:
        h *= sign
        if ax == "Z":
            out.append((cx + x, cy + y, cz + h))
        elif ax == "X":
            out.append((cx + h, cy + x, cz + y))
        else:
            out.append((cx + x, cy + h, cz + y))
    return mesh(name, out, faces, material, group, smooth_deg)


def cyl(name, r, h0, h1, material, center, axis="Z", segs=96, group=None):
    return revolve(name, [(0, h0), (r, h0), (r, h1), (0, h1)], material, center, axis, segs, group=group)


def tube(name, r_out, r_in, h0, h1, material, center, axis="Z", segs=96, group=None):
    return revolve(name, [(r_in, h0), (r_out, h0), (r_out, h1), (r_in, h1)], material, center, axis, segs,
                   closed=True, group=group)


def wire(name, points_mm, radius, material, group=None):
    """A round cable along a smooth curve through the given points."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius * MM
    cu.bevel_resolution = 6
    sp = cu.splines.new("NURBS")
    sp.points.add(len(points_mm) - 1)
    for p, (x, y, z) in zip(sp.points, points_mm):
        p.co = (x * MM, y * MM, z * MM, 1)
    sp.use_endpoint_u = True
    sp.order_u = 4
    sp.resolution_u = 24
    ob = bpy.data.objects.new(name, cu)
    SC.collection.objects.link(ob)
    cu.materials.append(material)
    OBJ[name] = ob
    GROUP[name] = group
    return ob


# ---- the assembly --------------------------------------------------------------------------
def import_part(stem, material, group):
    bpy.ops.wm.stl_import(filepath=str(HERE / "stl" / f"{stem}.stl"), global_scale=MM)
    ob = bpy.context.selected_objects[0]
    ob.name = stem
    return finish(ob, material, 30, group)


def build(M):
    import_part("base", M["print"], "base")
    import_part("lid", M["print"], "lid")
    import_part("sleeve", M["print"], "sleeve")

    # SKS 20 mL PET vial (wall ~1 mm assumed), white ribbed 22-400 cap, liquid to the fill line
    c = (VX, VY, VZ0)
    revolve("vial_glass", [
        (0, 0), (12.5, 0), (13.3, 0.25), (13.62, 0.9), (13.7, 1.6), (13.7, 46.8), (13.3, 48.2),
        (12.2, 49.3), (11.0, 49.9), (11.0, 58.6), (10.0, 58.6), (10.0, 50.3), (11.4, 49.0),
        (12.4, 48.0), (12.7, 46.8), (12.7, 1.8), (12.5, 1.2), (11.8, 1.05), (0, 1.05)],
        M["glass"], c, group="vial", smooth_deg=40)
    revolve("vial_liquid", [(0, 1.1), (11.75, 1.1), (12.45, 1.25), (12.64, 1.9), (12.64, FILL),
                            (0, FILL)], M["liquid"], c, group="vial", smooth_deg=40)
    ribs = lambda t: 0.22 * max(0.0, math.cos(90 * t)) ** 0.5  # 90 grip ribs
    revolve("vial_cap", [
        (0, 58.8), (11.05, 58.8), (11.05, 50.0), (11.9, 50.0), (12.13, 50.25, True),
        (12.13, 59.3, True), (11.95, 59.85), (11.5, 60.0), (0, 60.0)],
        M["cap"], c, segs=128 if DUMP else 720, rib=None if DUMP else ribs, group="vial", smooth_deg=50)

    # LEDs: lip 5.3 at the block face, body 4.6, dome; 5.1 long overall; legs out the back
    for color, z in LEDS:
        revolve(f"led_{color}", [(0, 0), (2.65, 0), (2.65, 1.0), (2.3, 1.0), (2.3, 2.8)]
                + [(2.3 * math.cos(a), 2.8 + 2.3 * math.sin(a)) for a in
                   [math.radians(d) for d in range(10, 91, 10)]],
                M["led_" + color], (LED_FACE_X - 1.0, VY, z), axis="X", segs=64, group="led")
        for k, dy in enumerate((-1.27, 1.27)):
            cyl(f"led_{color}_leg{k}", 0.25, 0.0, 9.0 + 1.5 * k, M["steel"],
                (LED_FACE_X - 1.0, VY + dy, z), axis="-X", segs=12, group="led_nocut")

    # TSL2591 board (EC Buying, ~16 x 19) in the 180 deg pocket, chip facing -X at the beam
    t = TSL
    box("tsl_pcb", (t["x0"], t["y0"], t["z0"]), (t["x1"], t["y1"], t["z1"]), M["pcb_tsl"], "tsl", bevel=0.2)
    box("tsl_chip", (t["x0"] - 0.65, VY - 1.0, BEAM_Z - 1.2), (t["x0"], VY + 1.0, BEAM_Z + 1.2), M["chip"], "tsl")
    box("tsl_window", (t["x0"] - 0.67, VY - 0.55, BEAM_Z - 0.55), (t["x0"] - 0.6, VY + 0.55, BEAM_Z + 0.55),
        M["window"], "tsl")
    for k, (dy, dz) in enumerate([(-4.5, -5.5), (4.0, -6.0), (-4.0, 5.0), (4.5, 4.0)]):
        box(f"tsl_smd{k}", (t["x0"] - 0.5, VY + dy - 0.6, BEAM_Z + dz - 0.3),
            (t["x0"], VY + dy + 0.6, BEAM_Z + dz + 0.3), M["chip"] if k % 2 else M["gold"], "tsl")
    hz = t["z1"] - 1.6
    box("tsl_header", (t["x1"], VY - 7.62, hz - 1.25), (t["x1"] + 2.5, VY + 7.62, hz + 1.25), M["black"], "tsl")
    for i in range(6):
        y = VY - 6.35 + 2.54 * i
        box(f"tsl_pin{i}", (t["x0"] - 1.0, y - 0.32, hz - 0.32), (t["x1"] + 8.5, y + 0.32, hz + 0.32), M["gold"], "tsl")

    # TCS34725 board (Adafruit, 20.3 square) in the 90 deg pocket, chip facing -Y at the beam
    t = TCS
    box("tcs_pcb", (t["x0"], t["y0"], t["z0"]), (t["x1"], t["y1"], t["z1"]), M["pcb_tcs"], "tcs", bevel=0.2)
    box("tcs_chip", (VX - 1.0, t["y0"] - 0.65, BEAM_Z - 1.2), (VX + 1.0, t["y0"], BEAM_Z + 1.2), M["chip"], "tcs")
    box("tcs_window", (VX - 0.55, t["y0"] - 0.67, BEAM_Z - 0.55), (VX + 0.55, t["y0"] - 0.6, BEAM_Z + 0.55),
        M["window"], "tcs")
    box("tcs_whiteled", (VX - 3.3 - 1.4, t["y0"] - 1.0, BEAM_Z - 1.0), (VX - 3.3 + 1.4, t["y0"], BEAM_Z + 1.0),
        M["white_led"], "tcs")
    for k, (dx, dz) in enumerate([(5.0, -5.0), (-5.5, 5.5), (5.5, 5.0), (0.0, -6.5)]):
        box(f"tcs_smd{k}", (VX + dx - 0.6, t["y0"] - 0.5, BEAM_Z + dz - 0.3),
            (VX + dx + 0.6, t["y0"], BEAM_Z + dz + 0.3), M["chip"] if k % 2 else M["gold"], "tcs")
    hz = t["z1"] - 1.6
    box("tcs_header", (VX - 8.89, t["y1"], hz - 1.25), (VX + 8.89, t["y1"] + 2.5, hz + 1.25), M["black"], "tcs")
    for i in range(7):
        x = VX - 7.62 + 2.54 * i
        box(f"tcs_pin{i}", (x - 0.32, t["y0"] - 1.0, hz - 0.32), (x + 0.32, t["y1"] + 8.5, hz + 0.32), M["gold"], "tcs")

    # 16x2 LCD (GDM1602K): PCB under the lid, bezel up through the window, flush with the lid top
    bx, by = BB
    box("lcd_pcb", (bx - 40, by - 18, 35.4), (bx + 40, by + 18, 37.0), M["pcb_lcd"], "lid", bevel=0.2)
    box("lcd_frame", (bx - 35.65, by - 13.15, 37.0), (bx + 35.65, by + 13.15, 43.9), M["lcd_frame"], "lid", bevel=0.4)
    scr = box("lcd_screen", (bx - 32.25, by - 8.2, 43.9), (bx + 32.25, by + 8.2, 43.95), M["lcd"], "lid")
    uv_top(scr)
    for k, (x, y) in enumerate(LCD_HOLES):
        revolve(f"lcd_screw{k}", [(0, 44.0), (2.25, 44.0), (2.25, 44.9), (1.9, 45.6), (0, 45.75)],
                M["steel"], (x, y, 0), segs=48, group="lid")
        cyl(f"lcd_nut{k}", 2.7, 33.4, 35.4, M["steel"], (x, y, 0), segs=6, group="lid")

    # M3 heat-set inserts (brass, flush with the post tops) and M3 x 6 button-head lid screws
    for k, (x, y) in enumerate(POSTS):
        tube(f"insert{k}", 2.4, 1.5, 38.2, 42.0, M["brass"], (x, y, 0), segs=48, group="base")
        revolve(f"screw{k}", [(0, 45.1), (1.0, 45.1), (1.0, 44.5), (0, 44.5)], M["black"], (x, y, 0),
                segs=6, group="screws")  # hex socket shadow
        revolve(f"screwhead{k}", [(0, 44.0), (2.85, 44.0), (2.85, 44.55), (2.4, 45.35), (1.2, 45.65),
                                  (1.2, 45.1), (0, 45.1)], M["steel"], (x, y, 0), segs=64, group="screws")
        cyl(f"screwshank{k}", 1.5, 38.0, 44.0, M["steel"], (x, y, 0), segs=32, group="screws")

    # breadboard (half size) with an ESP32 DevKitC straddling the channel, USB at the left wall
    box("bb_body", (bx - 42, by - 27.5, 2.0), (bx + 42, by + 27.5, 10.45), M["bb_body"], "base", bevel=0.6)
    top = box("bb_top", (bx - 41.6, by - 27.1, 10.45), (bx + 41.6, by + 27.1, 10.5), M["bb"], "base")
    uv_top(top)
    ex0, ex1 = 3.0, 57.4
    box("esp_pcb", (ex0, by - 13.95, 13.0), (ex1, by + 13.95, 14.6), M["pcb_esp"], "base", bevel=0.25)
    for side in (-1, 1):
        box(f"esp_hdr{side}", (ex0 + 3, by + side * 12.7 - 1.25, 10.5), (ex1 - 3, by + side * 12.7 + 1.25, 13.0),
            M["black"], "base")
        for i in range(19):
            x = ex0 + 4.4 + 2.54 * i
            cyl(f"esp_pin{side}_{i}", 0.45, 14.6, 15.3, M["gold"], (x, by + side * 12.7, 0), segs=12, group="base")
    box("esp_module", (ex1 - 25.5, by - 9.0, 14.6), (ex1 + 0.6, by + 9.0, 15.4), M["pcb_esp"], "base")
    box("esp_shield", (ex1 - 24.8, by - 8.0, 15.4), (ex1 - 7.0, by + 8.0, 17.8), M["shield"], "base", bevel=0.3)
    for k in range(5):  # antenna meander
        box(f"esp_ant{k}", (ex1 - 6.0 + 1.1 * k, by - 7.5, 15.4), (ex1 - 5.6 + 1.1 * k, by + 7.5, 15.45),
            M["gold"], "base")
    box("esp_usb", (2.4, by - 4.47, 14.6), (9.75, by + 4.47, 17.86), M["usb_metal"], "base", bevel=0.8)
    box("esp_uart", (12.0, by - 2.5, 14.6), (17.0, by + 2.5, 15.5), M["chip"], "base")
    box("esp_ldo", (19.0, by - 9.5, 14.6), (25.5, by - 6.0, 16.2), M["chip"], "base")
    for k, dy in enumerate((-9.5, 9.5)):
        box(f"esp_btn{k}", (5.5, by + dy - 1.8, 14.6), (9.0, by + dy + 1.8, 16.0), M["shield"], "base")
        cyl(f"esp_btncap{k}", 0.9, 16.0, 16.6, M["black"], (7.25, by + dy, 0), segs=24, group="base")

    # USB-C cable to the phone: plug in the left-wall port, cable dropping to the table
    zc = 16.23
    box("usb_shell", (-4.0, by - 4.1, zc - 1.25), (5.0, by + 4.1, zc + 1.25), M["usb_metal"], "usb", bevel=0.9)
    box("usb_mold", (-19.0, by - 6.0, zc - 3.1), (-1.5, by + 6.0, zc + 3.1), M["rubber"], "usb", bevel=2.2)
    wire("usb_cable", [(-18.0, by, zc), (-28.0, by, zc), (-40.0, by - 6, 6.0), (-52.0, by - 24, 1.9),
                       (-62.0, by - 60, 1.9), (-66.0, by - 110, 1.9), (-62.0, by - 170, 1.9)],
         1.9, M["rubber"], "usb")


def uv_top(ob):
    """Planar UVs over the top face's bounding rectangle (for the LCD / breadboard textures)."""
    me = ob.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    uv = me.uv_layers.new(name="UV")
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = ((co.x - min(xs)) / (max(xs) - min(xs)), (co.y - min(ys)) / (max(ys) - min(ys)))


def beams(M):
    """Light paths for the cutaway: each LED -> through the slit and the sample -> TSL2591 chip."""
    chip = Vector((TSL["x0"] - 0.65, VY - 0.6, BEAM_Z))
    for color, z in LEDS:
        a = Vector((LED_FACE_X + 4.1, VY - 0.6, z))
        d = chip - a
        rot = d.to_track_quat("Z", "Y")
        for kind, r in (("beam", 0.42), ("halo", 1.5)):
            ob = cyl(f"{kind}_{color}", r, 0.0, d.length, M[f"{kind}_{color}"], (0, 0, 0), segs=24,
                     group="beam")
            ob.rotation_mode = "QUATERNION"
            ob.rotation_quaternion = rot
            ob.location = a * MM
            ob.visible_shadow = False
    # side scatter towards the 90 deg window (TCS34725)
    for k, (dx, dz) in enumerate([(-3, -4), (2, -1), (-1, 3), (3, 5), (0, 0)]):
        a = Vector((VX + dx, VY + 2, BEAM_Z + dz))
        b = Vector((VX, 37.5, BEAM_Z))
        d = b - a
        ob = cyl(f"scatter{k}", 0.3, 0.0, d.length, M["halo_white"], (0, 0, 0), segs=16, group="beam")
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = d.to_track_quat("Z", "Y")
        ob.location = a * MM
        ob.visible_shadow = False


# ---- staging -------------------------------------------------------------------------------
EXPLODE = {"lid": 46.0, "screws": 66.0, "vial": 104.0, "sleeve": 124.0, "tsl": 30.0, "tcs": 42.0,
           "usb": (-22.0, 0.0, 0.0)}


def offset(group):
    if SHOT == "exploded":
        v = EXPLODE.get(group, 0.0)
        return Vector(v) if isinstance(v, tuple) else Vector((0, 0, v))
    if SHOT == "hero" and group in ("vial", "sleeve"):
        return Vector((0, 0, 60.0))
    return Vector((0, 0, 0))


def stage():
    for name, ob in OBJ.items():
        g = GROUP[name]
        if g == "led_nocut":
            g = "led"
        ob.location = ob.location + offset(g) * MM
    if SHOT != "hero":
        for name in [n for n in OBJ if GROUP[n] == "usb"]:
            if SHOT == "cutaway":
                bpy.data.objects.remove(OBJ.pop(name))


def cut(M, axis="y", value=YCUT):
    """Section cut. axis y: remove everything in front (y < value); axis z: everything above."""
    k = "xyz".index(axis)
    lo, hi = [-300, -300, -50], [400, 400, 400]
    if axis == "y":
        hi[1] = value
    else:
        lo[2] = value
    cutter = box("cutter", tuple(lo), tuple(hi), None)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for name in list(OBJ):
        ob = OBJ[name]
        if name == "cutter" or GROUP.get(name) in ("led", "led_nocut", "beam"):
            if GROUP.get(name) in ("led", "led_nocut"):
                bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
                cmin, cmax = min(p[k] for p in bb) / MM, max(p[k] for p in bb) / MM
                if (axis == "z" and cmin >= value) or (axis == "y" and cmax <= value - 3.0):
                    bpy.data.objects.remove(OBJ.pop(name))
            continue
        bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        cmin, cmax = min(p[k] for p in bb) / MM, max(p[k] for p in bb) / MM
        gone = cmax <= value if axis == "y" else cmin >= value
        whole = cmin >= value if axis == "y" else cmax <= value
        if gone:
            bpy.data.objects.remove(OBJ.pop(name))
            continue
        if whole or ob.type != "MESH":
            continue
        mod = ob.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        dg.update()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.clear()
        old = ob.data
        ob.data = me
        bpy.data.meshes.remove(old)
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(30))
        if name in ("base", "lid", "sleeve"):
            me.materials.append(M["section"])
            idx = len(me.materials) - 1
            sgn = -1 if axis == "y" else 1
            for p in me.polygons:
                if p.normal[k] * sgn > 0.99 and abs(p.center[k] / MM - value) < 0.01:
                    p.material_index = idx
    bpy.data.objects.remove(OBJ.pop("cutter"))


def dump(path):
    """Write every mesh as world-space triangles in mm (for lineart.py)."""
    import numpy as np
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    data, meta = {}, []
    for i, (name, ob) in enumerate(OBJ.items()):
        if ob.type not in ("MESH", "CURVE"):
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(ob.matrix_world)
        co = (co @ mw[:3, :3].T + mw[:3, 3]) / MM
        tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", tri)
        ev.to_mesh_clear()
        data[f"v{i}"] = co.astype(np.float32)
        data[f"t{i}"] = tri.reshape(-1, 3)
        meta.append({"i": i, "name": name, "group": GROUP.get(name)})
    np.savez_compressed(path, meta=json.dumps(meta), **data)
    print("dumped", len(meta), "objects ->", path)


# ---- lights, camera, render ----------------------------------------------------------------
def direction(az, el):
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def light(name, target, az, el, dist, power, size, color=(1, 1, 1), shape="DISK"):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.shape = shape
    ld.size = size
    ld.color = color
    if shape == "RECTANGLE":
        ld.size_y = size * 4
    ob = bpy.data.objects.new(name, ld)
    SC.collection.objects.link(ob)
    d = direction(az, el)
    ob.location = target + d * dist
    ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return ob


def world(color, strength):
    w = bpy.data.worlds.new("world")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength
    SC.world = w


def camera(target, az, el, lens, region, fit_objs):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cd.sensor_width = 36
    cam = bpy.data.objects.new("cam", cd)
    SC.collection.objects.link(cam)
    SC.camera = cam
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in fit_objs for c in o.bound_box]
    d = direction(az, el)
    dist = 1.0
    for _ in range(8):
        cam.location = target + d * dist
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        cd.shift_x = cd.shift_y = 0.0
        bpy.context.view_layer.update()
        ndc = [world_to_camera_view(SC, cam, p) for p in pts]
        xs, ys = [v.x for v in ndc], [v.y for v in ndc]
        s = max((max(xs) - min(xs)) / (region[2] - region[0]), (max(ys) - min(ys)) / (region[3] - region[1]))
        dist *= s
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    tx, ty = (region[0] + region[2]) / 2, 1 - (region[1] + region[3]) / 2
    cd.shift_x = cx - tx
    cd.shift_y = (cy - ty) * H / W
    bpy.context.view_layer.update()
    return cam


def project(cam, p_mm):
    v = world_to_camera_view(SC, cam, Vector(p_mm) * MM)
    return [round(v.x * W, 1), round((1 - v.y) * H, 1)]


def render_setup():
    SC.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    # RENDER_CPU=1 skips the GPU: Intel Arc (oneAPI) hit "device lost" on the hero and exploded shots.
    gpu_kinds = () if os.environ.get("RENDER_CPU") == "1" else ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
    for kind in gpu_kinds:
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devs = [d for d in prefs.devices if d.type == kind]
        if devs:
            for d in prefs.devices:
                d.use = d.type == kind
            SC.cycles.device = "GPU"
            print("render device:", kind, [d.name for d in devs])
            break
    cy = SC.cycles
    cy.samples = SAMPLES
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.012
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
        cy.denoising_use_gpu = True
    except (TypeError, AttributeError):
        pass
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 16, 4, 6
    cy.transmission_bounces, cy.transparent_max_bounces, cy.volume_bounces = 16, 16, 2
    cy.caustics_reflective = cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.film_transparent_glass = True
    SC.render.film_transparent = True
    SC.render.resolution_x, SC.render.resolution_y, SC.render.resolution_percentage = W, H, 100
    SC.render.image_settings.file_format = "PNG"
    SC.render.image_settings.color_mode = "RGBA"
    SC.render.image_settings.color_depth = "8"
    SC.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            SC.view_settings.look = look
            break
        except TypeError:
            pass


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    global SC, SHOT
    SC = bpy.context.scene
    if DUMP:
        SHOT = {"assembled": "assembled", "exploded": "exploded", "cut_y": "cutaway", "cut_z": "cut_z"}[DUMP]
        M = build_materials("light")
        build(M)
        stage()
        for name in [n for n in OBJ if GROUP[n] == "usb"]:
            if DUMP != "exploded" or name == "usb_cable":
                bpy.data.objects.remove(OBJ.pop(name))
        if DUMP == "cut_y":
            cut(M, "y", YCUT)
        elif DUMP == "cut_z":
            cut(M, "z", ZCUT)
        OUT.mkdir(exist_ok=True)
        dump(OUT / f"mesh_{DUMP}.npz")
        return
    theme = "light" if SHOT == "exploded" else "dark"
    M = build_materials(theme)
    build(M)
    stage()
    if SHOT == "cutaway":
        beams(M)
        cut(M)
    catcher = box("ground", (-1500, -1500, -0.02), (1500, 1500, 0.0), M["print"])
    catcher.is_shadow_catcher = True
    OBJ.pop("ground")

    fit = [o for n, o in OBJ.items() if GROUP.get(n) not in ("usb",)]
    if SHOT == "exploded":
        world((1.0, 1.0, 1.0), 0.55)
        tgt = Vector((46, 64, 95)) * MM
        cam = camera(tgt, -36, 24, 85, (0.24, 0.05, 0.76, 0.95), fit + [OBJ["usb_mold"]])
        light("key", tgt, -50, 52, 0.9, 16, 0.7)
        light("fill", tgt, 60, 22, 0.9, 6, 0.9)
        light("rim", tgt, 160, 35, 0.8, 14, 0.5)
        light("top", tgt, 0, 88, 0.8, 5, 0.6)
        SC.view_settings.exposure = 0.0
    elif SHOT == "hero":
        world((0.35, 0.45, 0.65), 0.025)
        tgt = Vector((46, 64, 40)) * MM
        cam = camera(tgt, -38, 21, 85, (0.30, 0.10, 0.80, 0.92), fit)
        light("key", tgt, -55, 45, 0.8, 9, 0.6)
        light("fill", tgt, 35, 15, 0.9, 1.6, 1.0, (0.85, 0.92, 1.0))
        light("rim_l", tgt, -150, 25, 0.7, 16, 0.25, (0.70, 0.85, 1.0), "RECTANGLE")
        light("rim_r", tgt, 145, 30, 0.7, 14, 0.25, (0.70, 0.85, 1.0), "RECTANGLE")
        light("top", tgt, 0, 85, 0.8, 3, 0.4)
    else:  # cutaway
        world((0.35, 0.45, 0.65), 0.03)
        tgt = Vector((46, 40, 32)) * MM
        cam = camera(tgt, -24, 15, 100, (0.08, 0.10, 0.70, 0.94),
                     [OBJ[n] for n in ("base", "sleeve", "vial_glass")])
        light("key", tgt, -40, 40, 0.8, 6, 0.6)
        light("fill", tgt, 30, 10, 0.9, 1.5, 1.0, (0.85, 0.92, 1.0))
        light("rim", tgt, 150, 35, 0.7, 10, 0.3, (0.7, 0.85, 1.0))
        light("top", tgt, -10, 80, 0.8, 2.5, 0.5)

    anchors = {
        "exploded": {
            "sleeve": (VX + 19.0, VY, 45.5 + 124 + 10), "vial": (VX + 13.7, VY, VZ0 + 104 + 30),
            "cap": (VX + 12.3, VY, VZ0 + 104 + 55), "lcd": (46, 94, 44 + 46), "lid": (8, 60, 44 + 46),
            "screws": (85.5, 122, 45.6 + 66), "tsl": (65.9, 21.6, 29.5 + 30), "tcs": (52, 41.5, 29.9 + 42),
            "led": (LED_FACE_X - 1, VY, 29), "esp32": (44, 88, 17.8), "breadboard": (84, 110, 10.5),
            "base": (0, 40, 22), "usb": (-19.0 - 22, 88, 19.3), "inserts": (6.5, 122, 42),
            "tsl_from": (65.1, 21.6, 10.5 + 30), "tsl_to": (65.1, 21.6, 25.5),
            "tcs_from": (46, 40.7, 9.6 + 42), "tcs_to": (46, 40.7, 26.0),
            "vial_from": (VX, VY, VZ0 + 104), "vial_to": (VX, VY, 51.0),
            "lid_from": (85.5, 6.5, 35.4 + 46), "lid_to": (85.5, 6.5, 42.0),
            "lid_from2": (6.5, 6.5, 35.4 + 46), "lid_to2": (6.5, 6.5, 42.0),
            "scr_from": (85.5, 6.5, 44 + 66), "scr_to": (85.5, 6.5, 44 + 46),
        },
        "hero": {
            "sleeve": (VX + 18.9, VY, 45.5 + 60 + 12), "vial": (VX + 13.7, VY, VZ0 + 60 + 20),
            "lcd": (46 + 30, 88, 44), "usb": (-10, 88, 19), "collar": (VX - 16.6, VY, 51),
            "base": (0, 30, 20),
        },
        "cutaway": {
            "led": (LED_FACE_X - 1, VY, 29), "slit": (30.4, VY, 31.4), "sample": (VX - 4, VY, 28),
            "tsl": (TSL["x0"] - 0.6, VY, BEAM_Z), "tcs": (VX, 38.2, BEAM_Z + 2.5),
            "sleeve": (VX + 17.6, VY, 52), "collar": (VX + 16.0, VY, 47.5), "cap": (VX, VY, 61.5),
            "lid": (80, VY, 44), "beam": (VX + 6, VY, 20.6), "bore": (VX - 14.1, VY, 8.0),
            "window": (61.4, VY, 22.5),
        },
    }[SHOT]
    render_setup()
    OUT.mkdir(exist_ok=True)
    meta = {"shot": SHOT, "size": [W, H], "anchors": {k: project(cam, v) for k, v in anchors.items()}}
    (OUT / f"{SHOT}.json").write_text(json.dumps(meta, indent=1))
    SC.render.filepath = str(OUT / f"{SHOT}.png")
    bpy.ops.render.render(write_still=True)
    print("wrote", SC.render.filepath)


main()
