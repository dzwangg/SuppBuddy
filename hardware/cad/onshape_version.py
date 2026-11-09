"""Create an Onshape document version (immutable snapshot) of the SuppBuddy workspace.
Usage: onshape-mcp/.venv/Scripts/python.exe cad/onshape_version.py V1 "description"
"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import osh
from build_enclosure import DID, WID, EID

async def main(name, desc):
    S = osh.Studio(DID, WID, EID)
    existing = await S.c.get(f"/api/v9/documents/d/{DID}/versions")
    if any(v["name"] == name for v in existing):
        raise SystemExit(f"version {name!r} already exists")
    v = await S.c.post(f"/api/v9/documents/d/{DID}/versions",
                       data={"documentId": DID, "workspaceId": WID, "name": name, "description": desc})
    print(f"created version {v['name']} id={v['id']} microversion={v.get('microversion')}")
    print(f"link: https://cad.onshape.com/documents/{DID}/v/{v['id']}/e/{EID}")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
