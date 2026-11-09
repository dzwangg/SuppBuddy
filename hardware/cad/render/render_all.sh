#!/usr/bin/env bash
# Render every shot: bash cad/render/render_all.sh [WxH] [samples] [shots...]
BL="/c/Program Files/Blender Foundation/Blender 5.1/blender.exe"
cd "$(dirname "$0")/../.."
RES=${1:-3840x2160}; SAMPLES=${2:-256}; shift 2 2>/dev/null
SHOTS=${*:-hero exploded cutaway}
for s in $SHOTS; do
  start=$(date +%s)
  "$BL" -b --factory-startup -P cad/render/scene.py -- --shot "$s" --res "$RES" --samples "$SAMPLES" 2>&1 \
    | grep -E "wrote|Error|error|Traceback|render device" | grep -v DeprecationWarning
  echo "$s: $(( $(date +%s) - start )) s"
done
