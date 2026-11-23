#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=================================================="
echo "  AoE2 Replay Chronicle · Camera Companion"
echo "=================================================="
echo ""
python3 "$DIR/AoE2ReviewHelper.app/Contents/Resources/helper.py" "$@"
