#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=================================================="
echo "  AoE2 Replay Chronicle · Camera Companion"
echo "=================================================="
echo ""

PYTHON_BIN="/usr/bin/python3"
for candidate in \
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" \
  "/usr/local/bin/python3" \
  "/opt/homebrew/bin/python3" \
  "/usr/bin/python3"; do
  if [ -x "$candidate" ]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

"$PYTHON_BIN" "$DIR/AoE2ReviewHelper.app/Contents/Resources/helper.py" "$@"
echo ""
echo "Helper finished. Press any key to close."
read -n 1 -s
