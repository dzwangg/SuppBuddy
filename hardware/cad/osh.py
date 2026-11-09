"""Tiny Onshape REST helpers for building fully-constrained, variable-driven Part Studio features.

Why not the MCP sketch tools? They leave rectangle positions unconstrained and only use the
default planes, so changing a variable doesn't move geometry predictably. Here every sketch
dimension/position is an expression of Part Studio variables (#name), so the model is truly
parametric in Onshape.

Coordinates: sketch units are mm; geometry is sent in meters (Onshape API native unit).
"""

import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "onshape-mcp"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "onshape-mcp" / ".env")

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials  # noqa: E402
import httpx  # noqa: E402
from loguru import logger  # noqa: E402

logger.remove()  # the MCP client logs every request at DEBUG; keep scripts quiet
logger.add(sys.stderr, level="WARNING")

MM = 0.001
PLANES = {"Top": "JDC", "Front": "JCC", "Right": "JEC"}


# ---------------------------------------------------------------- parameter helpers
def P_str(pid, value):
    return {"btType": "BTMParameterString-149", "value": value, "parameterId": pid}


def P_qty(pid, expr):
    return {"btType": "BTMParameterQuantity-147", "expression": expr, "parameterId": pid, "isInteger": False}


def P_enum(pid, enum, value):
    return {"btType": "BTMParameterEnum-145", "enumName": enum, "value": value, "parameterId": pid}


def P_bool(pid, value):
    return {"btType": "BTMParameterBoolean-144", "value": value, "parameterId": pid}


def P_ids(pid, ids):
    return {
        "btType": "BTMParameterQueryList-148",
        "queries": [{"btType": "BTMIndividualQuery-138", "deterministicIds": list(ids)}],
        "parameterId": pid,
    }


# ---------------------------------------------------------------- expression evaluation
class Vars:
    """Keeps Python-side values (mm) of Onshape variables so initial sketch geometry matches."""

    def __init__(self):
        self.v = {}

    def ev(self, expr):
        py = re.sub(r"#(\w+)", lambda m: f"V[{m.group(1)!r}]", str(expr))
        py = re.sub(r"(?<=\d)\s*mm\b", "", py)
        return float(eval(py, {"__builtins__": {}}, {"V": self.v}))


# ---------------------------------------------------------------- feature builders
def variable(name, expr, desc=""):
    return {
        "btType": "BTMFeature-134",
        "featureType": "assignVariable",
        "name": f"#{name}",
        "parameters": [
            P_enum("variableType", "VariableType", "LENGTH"),
            P_str("name", name),
            P_qty("lengthValue", expr),
            P_str("description", desc),
        ],
    }


def offset_plane(name, ref_id, offset_expr, flip=False):
    return {
        "btType": "BTMFeature-134",
        "featureType": "cPlane",
        "name": name,
        "parameters": [
            P_ids("entities", [ref_id]),
            P_enum("cplaneType", "CPlaneType", "OFFSET"),
            P_qty("offset", offset_expr),
            P_bool("oppositeDirection", flip),
        ],
    }


def extrude(name, sketch_fid, depth_expr, op="NEW", flip=False, scope_ids=None):
    params = [
        P_enum("operationType", "NewBodyOperationType", op),
        {
            "btType": "BTMParameterQueryList-148",
            "queries": [
                {
                    "btType": "BTMIndividualSketchRegionQuery-140",
                    "featureId": sketch_fid,
                    "filterInnerLoops": True,
                    "queryString": f'query = qSketchRegion(id + "{sketch_fid}", true);',
                    "deterministicIds": [],
                }
            ],
            "parameterId": "entities",
        },
        P_qty("depth", depth_expr),
        P_bool("oppositeDirection", flip),
    ]
    if scope_ids:
        params += [P_bool("defaultScope", False), P_ids("booleanScope", scope_ids)]
    return {"btType": "BTMFeature-134", "featureType": "extrude", "name": name, "parameters": params}


def fillet(name, edge_ids, radius_expr):
    return {
        "btType": "BTMFeature-134",
        "featureType": "fillet",
        "name": name,
        "parameters": [P_ids("entities", edge_ids), P_qty("radius", radius_expr)],
    }


class Sketch:
    """Fully-constrained sketch: every size/position is a variable expression measured from the origin."""

    def __init__(self, name, plane_id, V: Vars, origin_id):
        self.name, self.plane_id, self.V, self.origin_id = name, plane_id, V, origin_id
        self.ents, self.cons, self.n = [], [], 0

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def _con(self, ctype, params):
        self.cons.append(
            {"btType": "BTMSketchConstraint-2", "constraintType": ctype, "entityId": self._id("k"), "parameters": params}
        )

    def _origin(self):
        return P_ids("externalSecond", [self.origin_id])

    def _line(self, x0, y0, x1, y1):
        lid = self._id("l")
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        self.ents.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": lid,
                "startPointId": f"{lid}.start",
                "endPointId": f"{lid}.end",
                "startParam": 0.0,
                "endParam": length * MM,
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": x0 * MM,
                    "pntY": y0 * MM,
                    "dirX": (x1 - x0) / length,
                    "dirY": (y1 - y0) / length,
                },
                "isConstruction": False,
            }
        )
        return lid

    def rect(self, x, y, w, h):
        """Rectangle with min corner (x, y) and size (w, h); all args are Onshape expressions."""
        X, Y, Wd, H = (self.V.ev(e) for e in (x, y, w, h))
        b = self._line(X, Y, X + Wd, Y)
        r = self._line(X + Wd, Y, X + Wd, Y + H)
        t = self._line(X + Wd, Y + H, X, Y + H)
        lft = self._line(X, Y + H, X, Y)
        for a, c in ((b, r), (r, t), (t, lft), (lft, b)):
            self._con("COINCIDENT", [P_str("localFirst", f"{a}.end"), P_str("localSecond", f"{c}.start")])
        for ln, kind in ((b, "HORIZONTAL"), (t, "HORIZONTAL"), (lft, "VERTICAL"), (r, "VERTICAL")):
            self._con(kind, [P_str("localFirst", ln)])
        for ln, expr in ((b, w), (lft, h)):
            self._con(
                "LENGTH",
                [
                    P_str("localFirst", ln),
                    P_enum("direction", "DimensionDirection", "MINIMUM"),
                    P_qty("length", expr),
                    P_enum("alignment", "DimensionAlignment", "ALIGNED"),
                ],
            )
        if X == 0 and Y == 0:
            self._con("COINCIDENT", [P_str("localFirst", f"{b}.start"), self._origin()])
        else:
            for ln, expr in ((lft, x), (b, y)):
                self._con(
                    "DISTANCE",
                    [
                        P_str("localFirst", ln),
                        self._origin(),
                        P_enum("direction", "DimensionDirection", "MINIMUM"),
                        P_qty("length", expr),
                    ],
                )
        return self

    def rect_c(self, cx, cy, w, h):
        """Rectangle centred on (cx, cy)."""
        return self.rect(f"{cx} - ({w}) / 2", f"{cy} - ({h}) / 2", w, h)

    def circle(self, cx, cy, d):
        CX, CY, D = (self.V.ev(e) for e in (cx, cy, d))
        cid = self._id("c")
        self.ents.append(
            {
                "btType": "BTMSketchCurve-4",
                "entityId": cid,
                "centerId": f"{cid}.center",
                "geometry": {
                    "btType": "BTCurveGeometryCircle-115",
                    "radius": D / 2 * MM,
                    "xCenter": CX * MM,
                    "yCenter": CY * MM,
                    "xDir": 1.0,
                    "yDir": 0.0,
                    "clockwise": False,
                },
                "isConstruction": False,
            }
        )
        self._con("DIAMETER", [P_str("localFirst", cid), P_qty("length", d)])
        for direction, expr in (("HORIZONTAL", cx), ("VERTICAL", cy)):
            self._con(
                "DISTANCE",
                [
                    P_str("localFirst", f"{cid}.center"),
                    self._origin(),
                    P_enum("direction", "DimensionDirection", direction),
                    P_qty("length", expr),
                ],
            )
        return self

    def feature(self):
        return {
            "btType": "BTMSketch-151",
            "featureType": "newSketch",
            "name": self.name,
            "parameters": [P_ids("sketchPlane", [self.plane_id])],
            "entities": self.ents,
            "constraints": self.cons,
        }


# ---------------------------------------------------------------- Part Studio session
def _fsval(v):
    """Convert Onshape BTFSValue JSON into plain Python."""
    if not isinstance(v, dict):
        return v
    bt = v.get("btType", "")
    val = v.get("value")
    if bt.endswith("BTFSValueArray"):
        return [_fsval(x) for x in val]
    if bt.endswith("BTFSValueMap"):
        return {_fsval(e["key"]): _fsval(e["value"]) for e in val}
    return val


class Studio:
    def __init__(self, did, wid, eid):
        self.did, self.wid, self.eid = did, wid, eid
        self.c = OnshapeClient(
            OnshapeCredentials(
                access_key=os.environ["ONSHAPE_ACCESS_KEY"], secret_key=os.environ["ONSHAPE_SECRET_KEY"]
            )
        )

    @property
    def path(self):
        return f"/api/v9/partstudios/d/{self.did}/w/{self.wid}/e/{self.eid}"

    async def _call(self, method, *args, **kwargs):
        """Call the API, backing off and retrying when Onshape rate-limits us (HTTP 429)."""
        delay = 2
        for attempt in range(8):
            try:
                return await getattr(self.c, method)(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429 or attempt == 7:
                    raise
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def get(self, path, **kw):
        return await self._call("get", path, **kw)

    async def post(self, path, **kw):
        return await self._call("post", path, **kw)

    async def delete(self, path, **kw):
        return await self._call("delete", path, **kw)

    async def add(self, feature):
        r = await self.post(self.path + "/features", data={"btType": "BTFeatureDefinitionCall-1406", "feature": feature})
        fid = r["feature"]["featureId"]
        status = (r.get("featureState") or {}).get("featureStatus")
        if status != "OK":
            raise RuntimeError(f"Feature {feature.get('name')!r} ({fid}) status {status}")
        return fid

    async def update(self, fid, feature):
        feature = dict(feature, featureId=fid)
        r = await self.post(
            self.path + f"/features/featureid/{fid}", data={"btType": "BTFeatureDefinitionCall-1406", "feature": feature}
        )
        return (r.get("featureState") or {}).get("featureStatus")

    async def features(self):
        return await self.get(self.path + "/features")

    async def fs(self, body):
        r = await self.post(
            f"/api/v8/partstudios/d/{self.did}/w/{self.wid}/e/{self.eid}/featurescript",
            data={"script": body},
            params={"rollbackBarIndex": -1},
        )
        if r.get("notices"):
            for n in r["notices"]:
                msg = n.get("message") if isinstance(n, dict) else n
                if isinstance(msg, dict):
                    msg = msg.get("message")
                if msg:
                    print("  FS notice:", msg)
        return _fsval(r.get("result"))

    async def ids(self, query_fs):
        """Deterministic IDs for a FeatureScript query expression."""
        return await self.fs(
            f"function(context is Context, queries is map) {{ return transientQueriesToStrings(evaluateQuery(context, {query_fs})); }}"
        )

    async def created(self, fid, kind="BODY"):
        return await self.ids(f'qCreatedBy(makeId("{fid}"), EntityType.{kind})')

    async def box(self, query_fs):
        """Tight bounding box (mm) of a query: [xmin, ymin, zmin, xmax, ymax, zmax]."""
        return await self.fs(
            "function(context is Context, queries is map) { "
            f'var b = evBox3d(context, {{"topology": {query_fs}, "tight": true}}); '
            "return [b.minCorner[0] / millimeter, b.minCorner[1] / millimeter, b.minCorner[2] / millimeter, "
            "b.maxCorner[0] / millimeter, b.maxCorner[1] / millimeter, b.maxCorner[2] / millimeter]; }"
        )
