"""Seed crowd fingerprints so the demo has references to compare against.

  python -m scripts.seed_demo              # simulated scans (marked synthetic), protocol v3 cycles
  python -m scripts.seed_demo --runs 8

TODO(calibrate): this is a stopgap. Before judging, replace with REAL rig scans:
scan each demo product 5x through the app and hit "confirm". Real data wins, and the
report will stop saying "reference includes simulated demo scans".
"""
from __future__ import annotations

import argparse
import asyncio

from app import sim
from app.db import Scan, init_db, session
from app.fingerprints import update_fingerprint
from app.pipeline import run_scan
from app.schemas import ScanCreate

GENUINE = ["b_complex", "vitamin_c", "iron", "protein", "creatine"]


async def main(runs: int) -> None:
    init_db()
    for profile in GENUINE:
        for i in range(runs):
            body = ScanCreate.model_validate({"label": sim.PROFILES[profile]["label"],
                                              "readings": sim.generate(profile, seed=1000 + i), "synthetic": True})
            with session() as s:
                scan = Scan(label=body.label.model_dump(), readings=body.readings.model_dump(),
                            device_id="seed", synthetic=True, status="pending", revision=0, stages={})
                s.add(scan)
                s.flush()
                sid = scan.id
            await run_scan(sid)
            with session() as s:
                scan = s.get(Scan, sid)
                if scan.qc.get("ok") and scan.product_id:
                    update_fingerprint(s, scan.product_id, scan.features, body.readings.protocol, synthetic=True)
                    scan.confirmed = True
        print(f"seeded {profile}: {runs} scans")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    asyncio.run(main(ap.parse_args().runs))
