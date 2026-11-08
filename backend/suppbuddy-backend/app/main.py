"""SuppBuddy API. Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  (docs at /docs)"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app import llm, pipeline, sim
from app.config import settings
from app.db import Fingerprint, Product, Scan, init_db, session
from app.evidence import tainted
from app.fingerprints import fingerprint_stats, update_fingerprint
from app.schemas import ConfirmRequest, LabelInfo, ScanCreate
from app.scoring.accuracy import score_against_crowd
from app.scoring.verdict import lcd_message

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    swept = pipeline.sweep_stale()
    if swept:
        logging.getLogger("suppbuddy").warning("settled %d scan(s) left mid-run by the previous process", swept)
    yield


def require_token(authorization: str | None = Header(None)) -> None:
    """One shared token from .env (API_TOKEN). Unset = open, for the Simulator against localhost. Set it before
    the server is reachable beyond your laptop: every endpoint can spend Claude credits or feed the crowd data."""
    if settings.api_token and authorization != f"Bearer {settings.api_token}":
        raise HTTPException(401, "missing or wrong API token (Settings > API token in the app)")


app = FastAPI(title="SuppBuddy API", version="0.1.0", lifespan=lifespan, dependencies=[Depends(require_token)])
# TODO(mobile): lock origins down if you ship a web client; native iOS doesn't need CORS.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def _validation_error(_, exc: RequestValidationError) -> JSONResponse:
    # The default handler echoes the rejected input; a NaN there can't be serialized and turns the 422 into a 500.
    return JSONResponse(status_code=422,
                        content={"detail": jsonable_encoder([{k: v for k, v in e.items() if k != "input"} for e in exc.errors()])})


def envelope(scan: Scan) -> dict:
    return {
        "id": scan.id,
        "status": scan.status,
        "revision": scan.revision,
        "device_id": scan.device_id,
        "product_id": scan.product_id,
        "confirmed": scan.confirmed,
        "synthetic": scan.synthetic,
        "label": scan.label,
        "features": scan.features,
        "qc": scan.qc,
        "report": scan.report,
        "stages": scan.stages,
        "lcd": lcd_message(scan.status, scan.report).model_dump(),
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
    }


def _load(scan_id: str) -> Scan:
    with session() as s:
        scan = s.get(Scan, scan_id)
        if not scan:
            raise HTTPException(404, "scan not found")
        return scan


@app.get("/health")
def health():
    return {"ok": True, "llm": llm.available(), "model": settings.llm_model,
            "evidence_offline": settings.evidence_offline, "tainted": tainted.status(),
            "protocol": settings.protocol_version}


# ---------------------------------------------------------------------------
# Label vision
# ---------------------------------------------------------------------------
@app.post("/label/extract", response_model=LabelInfo)
async def extract_label(images: list[UploadFile] = File(...)):
    """Upload 1-3 photos (front + Supplement Facts panel). Returns structured label for the user to confirm."""
    if not llm.available():
        raise HTTPException(503, "ANTHROPIC_API_KEY not set; send label fields manually in POST /scans")
    from app.vision import extract_label as _extract
    payload = []
    for f in images[:3]:
        if (f.size or 0) > 8_000_000:  # read() would hold it all in memory; the API rejects >5 MB images anyway
            raise HTTPException(413, "each photo must be under 8 MB")
        payload.append((await f.read(), f.content_type or "image/jpeg"))
    # The iOS app sends JPEG (UIImage.jpegData); HEIC isn't an accepted image type.
    try:
        return await _extract(payload)
    except Exception as e:  # noqa: BLE001 - surface the reason to the app instead of a bare 500
        raise HTTPException(502, f"label reading failed: {type(e).__name__}: {e}"[:300]) from e


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------
@app.post("/scans", status_code=202)
async def create_scan(body: ScanCreate, wait: bool = Query(False, description="Block until done (debug/tests)")):
    if not body.label and not body.readings and not body.product_id:
        raise HTTPException(422, "send at least one of label, readings, product_id")
    with session() as s:
        scan = Scan(
            device_id=body.readings.device_id if body.readings else None,
            product_id=body.product_id,
            label=body.label.model_dump() if body.label else None,
            readings=body.readings.model_dump() if body.readings else None,
            sample_prep=body.sample_prep.model_dump() if body.sample_prep else None,
            synthetic=body.synthetic,
            status="pending", revision=0, stages={},
        )
        s.add(scan)
        s.flush()
        scan_id = scan.id
    if wait:
        await pipeline._run_safely(scan_id)
    else:
        pipeline.start(scan_id)
    return envelope(_load(scan_id))


@app.get("/scans/{scan_id}")
def get_scan(scan_id: str):
    return envelope(_load(scan_id))


@app.get("/scans/{scan_id}/lcd")
def get_lcd(scan_id: str):
    """Compact message for the device LCD. Phone polls this and forwards to the ESP32."""
    scan = _load(scan_id)
    return lcd_message(scan.status, scan.report)


@app.post("/scans/{scan_id}/research", status_code=202)
async def rerun(scan_id: str, wait: bool = False):
    _load(scan_id)
    if wait:
        await pipeline._run_safely(scan_id)
    else:
        pipeline.start(scan_id)
    return envelope(_load(scan_id))


@app.post("/scans/{scan_id}/confirm")
def confirm(scan_id: str, body: ConfirmRequest | None = None):
    """User confirms product identity. Only confirmed, QC-passing scans feed the crowd fingerprint.

    Once a product has an established reference, a scan that's inconsistent with it is held instead of
    merged ({"held": true, ...}): it could be a fake, a bad prep, or someone poisoning the data, and one
    bad scan in a reference of 3-5 would corrupt it. Send {"force": true} to merge it after review."""
    with session() as s:
        scan = s.get(Scan, scan_id)
        if not scan:
            raise HTTPException(404, "scan not found")
        if scan.confirmed:
            raise HTTPException(409, "already confirmed")
        if body and body.product_id:
            if not s.get(Product, body.product_id):
                raise HTTPException(404, "product not found")
            scan.product_id = body.product_id
        if not scan.product_id:
            raise HTTPException(422, "scan has no product; pass product_id")
        if not scan.features or not (scan.qc or {}).get("ok"):
            raise HTTPException(422, "scan failed QC; not adding to reference data")
        protocol = (scan.readings or {}).get("protocol", settings.protocol_version)
        existing = s.get(Fingerprint, (scan.product_id, protocol))
        if existing and existing.n >= settings.min_fingerprint_n and not (body and body.force):
            check = score_against_crowd(scan.features, fingerprint_stats(existing), existing.n, existing.synthetic)
            if check.label == "inconsistent":
                held = {"status": "held", "distance": check.distance, "max_z": check.max_z,
                        "top_deviations": check.top_deviations}
                scan.stages = {**(scan.stages or {}), "confirm": held}
                scan.revision += 1
                return {"held": True, "product_id": scan.product_id, "protocol": protocol, "n": existing.n,
                        "synthetic": existing.synthetic,
                        "reason": f"This scan doesn't match the {existing.n} confirmed scans of this product, "
                                  "so it was held for review instead of added to the reference."}
        fp = update_fingerprint(s, scan.product_id, scan.features, protocol, scan.synthetic)
        scan.confirmed = True
        scan.revision += 1
        return {"held": False, "product_id": scan.product_id, "protocol": protocol, "n": fp.n,
                "synthetic": fp.synthetic, "features": fingerprint_stats(fp)}


@app.get("/scans")
def list_scans(device_id: str | None = None, product_id: str | None = None, limit: int = 20):
    with session() as s:
        q = select(Scan).order_by(Scan.created_at.desc()).limit(min(limit, 100))
        if device_id:
            q = q.where(Scan.device_id == device_id)
        if product_id:
            q = q.where(Scan.product_id == product_id)
        return [{"id": x.id, "status": x.status, "product_id": x.product_id, "confirmed": x.confirmed,
                 "verdict": (x.report or {}).get("verdict"), "created_at": x.created_at.isoformat()}
                for x in s.scalars(q)]


# ---------------------------------------------------------------------------
# Products / crowd data
# ---------------------------------------------------------------------------
@app.get("/products")
def list_products(q: str | None = None, limit: int = 20):
    with session() as s:
        stmt = select(Product).limit(min(limit, 100))
        if q:
            stmt = stmt.where(Product.id.contains(q.lower()))
        out = []
        for p in s.scalars(stmt):
            fps = s.scalars(select(Fingerprint).where(Fingerprint.product_id == p.id)).all()
            out.append({"id": p.id, "brand": p.brand, "name": p.name,
                        "scans": {fp.protocol: fp.n for fp in fps}})
        return out


@app.get("/products/{product_id}/fingerprint")
def product_fingerprint(product_id: str, protocol: str | None = None):
    with session() as s:
        fp = s.get(Fingerprint, (product_id, protocol or settings.protocol_version))
        if not fp:
            raise HTTPException(404, "no fingerprint for this product/protocol yet")
        return {"product_id": product_id, "protocol": fp.protocol, "n": fp.n, "synthetic": fp.synthetic,
                "features": fingerprint_stats(fp)}


# ---------------------------------------------------------------------------
# Dev helpers (David can hit these before the rig exists)
# ---------------------------------------------------------------------------
@app.get("/dev/profiles")
def dev_profiles():
    return {k: {kk: vv for kk, vv in v.items() if kk != "label"} | {"label": v["label"]} for k, v in sim.PROFILES.items()}


@app.get("/dev/readings")
def dev_readings(profile: str = "b_complex", led_mode: str = "cycle", seed: int | None = None):
    """Raw simulated device payload: the exact shape the phone should POST in `readings`."""
    if profile not in sim.PROFILES:
        raise HTTPException(404, f"unknown profile; try {list(sim.PROFILES)}")
    return sim.generate(profile, led_mode=led_mode, seed=seed)


@app.post("/dev/simulate", status_code=202)
async def dev_simulate(profile: str = "b_complex", wait: bool = True, seed: int | None = None):
    if profile not in sim.PROFILES:
        raise HTTPException(404, f"unknown profile; try {list(sim.PROFILES)}")
    body = ScanCreate.model_validate({
        "label": sim.PROFILES[profile]["label"],
        "readings": sim.generate(profile, seed=seed),
        "synthetic": True,
    })
    return await create_scan(body, wait=wait)
