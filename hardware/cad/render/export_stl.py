"""Export the printed parts of a saved Onshape version as binary STL (mm) for the renders.

    onshape-mcp/.venv/Scripts/python.exe cad/render/export_stl.py            # V3
    onshape-mcp/.venv/Scripts/python.exe cad/render/export_stl.py <versionId>

Writes cad/render/stl/<part>.stl (base, lid, sleeve). About 4 API calls (parts list + one STL per
part); none of them use the FeatureScript-eval quota.
"""

import base64
import os
import struct
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "onshape-mcp" / ".env")

DID = "ada0757f8a367ed8c935f14f"
EID = "5da49a2f1204f18bc3cad3cc"
V3 = "b4de7f1d731ede50c02bbeee"
OUT = Path(__file__).with_name("stl")
FILES = {"Base": "base", "Lid": "lid", "Vial cap sleeve": "sleeve"}
API = "https://cad.onshape.com/api/v9"


def main():
    vid = sys.argv[1] if len(sys.argv) > 1 else V3
    key = f"{os.environ['ONSHAPE_ACCESS_KEY']}:{os.environ['ONSHAPE_SECRET_KEY']}"
    auth = {"Authorization": "Basic " + base64.b64encode(key.encode()).decode()}
    OUT.mkdir(exist_ok=True)
    with httpx.Client(timeout=180) as c:
        r = c.get(f"{API}/parts/d/{DID}/v/{vid}/e/{EID}", headers={**auth, "Accept": "application/json"})
        r.raise_for_status()
        for part in r.json():
            stem = FILES.get(part["name"])
            if not stem:
                print("skip", part["name"])
                continue
            params = {
                "partIds": part["partId"],
                "mode": "binary",
                "units": "millimeter",
                "angleTolerance": 0.04,  # radians: ~157 facets per full circle
                "chordTolerance": 0.005,
            }
            r = c.get(f"{API}/partstudios/d/{DID}/v/{vid}/e/{EID}/stl", params=params,
                      headers={**auth, "Accept": "*/*"})
            for _ in range(5):  # follow redirects by hand so the auth header survives a host change
                if r.status_code not in (301, 302, 303, 307, 308):
                    break
                r = c.get(r.headers["location"], headers={**auth, "Accept": "*/*"})
            r.raise_for_status()
            data = r.content
            n = struct.unpack_from("<I", data, 80)[0]
            assert len(data) == 84 + 50 * n, f"{stem}: not a binary STL ({len(data)} bytes)"
            (OUT / f"{stem}.stl").write_bytes(data)
            print(f"{part['name']:16s} {part['partId']:6s} -> stl/{stem}.stl  {n} triangles"
                  f"  (rate-limit remaining {r.headers.get('x-rate-limit-remaining', '?')})")


if __name__ == "__main__":
    main()
