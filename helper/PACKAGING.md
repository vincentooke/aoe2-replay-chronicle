# Helper packaging — how the launch/video-pickup gap is closed

Problem (static page, proven): a browser page cannot launch a local
program or read a local file uninvited. So a static test page could
never be "click Review my game and everything after that is automated".

Solution (this product): a small companion program, installed once.

## What the user does — exactly once, no Terminal
1. Website -> "Download helper installer" -> a normal installer
   (.pkg/.dmg installer on Mac, .exe installer on Windows).
2. Double-click it, accept the one system approval the OS shows
   (Screen Recording / accessibility, presented by the installer itself).
3. Done. From then on, "Launch helper" on the website is one click.

## What the installer bundles (so the user installs nothing by hand)
- This helper's logic (helper.py, compiled with PyInstaller to a
  single app/exe — the user never sees Python, pip, or a script).
- ffmpeg, bundled next to the helper binary (helper.py searches
  ./ffmpeg and ./bin/ffmpeg first). No brew/apt/pip at runtime.
- Input automation bundled in the app (not pyautogui installed by the
  user). On Mac: AppleScript/System Events + screencapture via the
  bundled ffmpeg AVFoundation path. On Windows: Win32 input APIs.
- Protocol handler registration: `aoe2review://job/<id>?token=<token>`.
  Clicking Launch on the website starts the already-installed helper
  with that job. If it is not installed, the browser shows the
  download page instead — the website never tries to read local files.

## What the helper does per job (opt-in only)
1. Validates the job from the website: platform, replay choice, opt-in.
   If anything is missing, it stops and does nothing.
2. Window gate: game window frontmost AND >=75% of the screen, on
   every macOS Space (Mac) / foreground window + rect (Windows).
   Fail -> click nothing, record nothing, exit with a clear error.
3. Loads ONLY the chosen replay, sets All Visible ON / View Lock OFF,
   zooms out, runs the camera tour (named rotation for team games),
   keeps the session alive (Space every 2 min for GeForce idle),
   records with bundled ffmpeg.
4. Uploads the finished video directly to the website for that job
   (POST /api/jobs/<id>/upload, job token, one use). GeForce: video
   only, never the saved-games-folder path. Windows/Mac: also uploads
   the .aoe2record file from the game's save folder for parser numbers.
5. Exits. No login item, no background service, no auto-record.

## What is NOT in the product flow
- No Terminal commands, no `pip install`, no `brew install`.
- No GeForce Record as a core path (Ultimate-only). It may later be
  an optional bonus path for Ultimate users, behind the same opt-in
  job, but the bundled-ffmpeg path must work without it.
- No background recording, no recording every game.

## Build status after phase 2 (see BUILD_LOG)
- PyInstaller spec written (helper/aoe2review.spec, bundled ffmpeg,
  build fails without it) + installer templates (macOS Info.plist,
  Windows .iss + .reg, both registering aoe2review://) +
  helper/build_installer.py --check (passes here). NO installer was
  actually built in this VM (PyInstaller not installed), and no
  signing/notarisation exists — both are open launch items.
- Win32 foreground/coverage gate + macOS bounds gate implemented
  in helper.py, fail-closed, pure parts tested. Neither branch has
  run on its real OS yet (needs a real Windows machine / Vincent's Mac).
- Real capture + Space switching test on Vincent's Mac (needs him),
  and a real Windows/Steam run (needs a Windows machine he has).
- Parser on a real .aoe2record (needs mgz-fast on a Windows/Mac
  machine) — the loud-failure path is what was tested here.
