# PyInstaller spec — AoE2 Game Review helper (one-time installer payload).
#
# Build (by a developer, NOT by the end user):
#   pyinstaller helper/aoe2review.spec
# The end user never runs this, never sees Python, pip, or a script.
# They double-click the installer produced from this spec (see
# helper/installer/), which bundles ffmpeg and registers the
# aoe2review:// protocol handler.
#
# What is bundled:
# - helper.py + parser.py (the helper logic; parser is Windows/Mac only,
#   GeForce jobs never call it)
# - ffmpeg, bundled next to the binary. helper.py searches ./ffmpeg
#   and ./bin/ffmpeg FIRST, before any system ffmpeg. If the bundled
#   binary is missing at build time, the build FAILS (see the check
#   below) — the installer must never ship without ffmpeg, because
#   a runtime install step is not part of the product flow.
#
# What is NOT in this spec:
# - Signing / notarisation (macOS) or a signed Windows installer.
#   Those are open launch items (BUILD_LOG B3-adjacent): the spec
#   builds an unsigned app/exe for testing only. Do NOT present an
#   unsigned build as a release, and do NOT invent a certificate.
# - Any Terminal, pip, or brew step for the end user.
# - GeForce Record as a core path (Ultimate-only; see ARCHITECTURE.md).
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(SPEC))
HELPER_DIR = os.path.join(HERE, "helper")
# Bundled ffmpeg: prefer a ffmpeg binary placed in helper/bin/ by the
# developer before building; fall back to the system ffmpeg ONLY as a
# build-time source to copy in (the shipped binary is still bundled).
FFMPEG_CANDIDATES = [
    os.path.join(HELPER_DIR, "bin", "ffmpeg"),
    os.path.join(HELPER_DIR, "bin", "ffmpeg.exe"),
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
]
_ffmpeg = next((c for c in FFMPEG_CANDIDATES if os.path.isfile(c)), None)
if _ffmpeg is None:
    raise SystemExit(
        "BUILD FAILED: no ffmpeg binary found to bundle. Place one in "
        "helper/bin/ffmpeg (or ffmpeg.exe on Windows) and rebuild. "
        "The product must never ship without bundled ffmpeg."
    )

a = Analysis(
    [os.path.join(HELPER_DIR, "helper.py")],
    pathex=[HELPER_DIR],
    binaries=[(_ffmpeg, ".")],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="aoe2review-helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # UNSIGNED build for testing only (see header).
)

# macOS .app wrapper: the installer (helper/installer/Info.plist)
# adds CFBundleURLTypes for aoe2review://. This spec alone does not
# register a protocol handler — registration is an installer step,
# verified on a real Mac, not claimed here.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="AoE2ReviewHelper.app",
        icon=None,
        bundle_identifier="com.aoe2review.helper",
        info_plist={
            "CFBundleURLTypes": [
                {
                    "CFBundleURLName": "aoe2review",
                    "CFBundleURLSchemes": ["aoe2review"],
                }
            ],
        },
    )
