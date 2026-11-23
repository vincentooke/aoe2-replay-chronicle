#!/usr/bin/env python3
"""Check / build the helper installer payload (developer tool, not user flow).

--check (default): verifies, without claiming a build, that
  * helper/aoe2review.spec exists and parses as Python,
  * the spec bundles an ffmpeg binary (fails the build if none),
  * the macOS Info.plist template registers aoe2review://,
  * the Windows .iss + .reg register aoe2review://,
  * PyInstaller is importable (if not, reports it plainly and stops —
    it does NOT fall back to shipping a bare script as an installer).
--build: runs PyInstaller on the spec if importable; otherwise exits
  non-zero with the same plain report. A successful build here still
  does NOT mean a signed/notarised installer, a tested protocol
  handler, or a real Mac/Windows capture — those remain open items
  in BUILD_LOG.md and must be verified on real machines.
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "helper")


def check():
    errors, notes = [], []
    spec = os.path.join(HELPER, "aoe2review.spec")
    if not os.path.isfile(spec):
        errors.append("missing helper/aoe2review.spec")
    else:
        try:
            tree = ast.parse(open(spec).read())
            src = open(spec).read()
            for needle in ("ffmpeg", "aoe2review-helper", "CFBundleURLSchemes"):
                if needle not in src:
                    errors.append(f"spec missing {needle!r}")
            notes.append(f"spec parses as Python ({len(tree.body)} top-level nodes)")
        except SyntaxError as e:
            errors.append(f"spec does not parse: {e}")
    plist = os.path.join(HELPER, "installer", "Info.plist")
    if not os.path.isfile(plist) or "aoe2review" not in open(plist).read():
        errors.append("macOS Info.plist template missing aoe2review scheme")
    iss = os.path.join(HELPER, "installer", "aoe2review.iss")
    reg = os.path.join(HELPER, "installer", "windows_protocol.reg")
    if not os.path.isfile(iss) or "aoe2review" not in open(iss).read():
        errors.append("Windows .iss missing aoe2review protocol registration")
    if not os.path.isfile(reg) or "aoe2review" not in open(reg).read():
        errors.append("Windows .reg template missing aoe2review protocol registration")
    try:
        import PyInstaller  # noqa: F401
        notes.append(f"PyInstaller available ({PyInstaller.__version__})")
        pyinstaller = True
    except ImportError:
        notes.append("PyInstaller NOT importable in this Python — build cannot run here")
        pyinstaller = False
    # Bundled ffmpeg source for the build (developer machine only).
    cands = [os.path.join(HELPER, "bin", "ffmpeg"), "/usr/bin/ffmpeg",
             "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    found = next((c for c in cands if os.path.isfile(c)), None)
    notes.append(f"ffmpeg source for bundling: {found or 'NONE (build must fail)'}")
    if found is None:
        errors.append("no ffmpeg binary available to bundle")
    return errors, notes, pyinstaller


def main():
    build = "--build" in sys.argv
    errors, notes, pyinstaller = check()
    for n in notes:
        print(f"  {n}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        return 2
    if build and not pyinstaller:
        print("ERROR: cannot build without PyInstaller; install it in a developer "
              "environment only (never as an end-user step) and re-run.")
        return 3
    if build:
        import subprocess
        r = subprocess.run([sys.executable, "-m", "PyInstaller",
                            os.path.join(HELPER, "aoe2review.spec")],
                           capture_output=True, text=True, timeout=600)
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        return r.returncode
    print("CHECK OK: spec + installer templates are consistent; "
          "no installer was built, no signing is claimed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
