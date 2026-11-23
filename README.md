# AoE2 Game Review — final product (in progress, NOT launched)

A public website with account login and saved reviews per user, plus a
one-time helper installer that closes the gap a static page could not:
launching the recording and getting the video back without the user
picking files by hand or using Terminal.

**Status: skeleton only. Nothing here is published, priced, or ready
for Vincent to test.** See `BUILD_LOG.md` for verified vs unproven.

## Run the skeleton locally (developers only)
```bash
python3 app/server.py --port 8000
# open http://127.0.0.1:8000 — create an account, pick a platform,
# check opt-in, create a job, launch/download the helper.
python3 tests/test_end_to_end.py   # full verified flow
```

## Layout
- `app/server.py` — website + API (stdlib only)
- `app/analysis.py` — video-first review engine + clips
- `web/` — platform-first frontend
- `helper/helper.py` — companion logic (packaged as an installer)
- `helper/PACKAGING.md` — how the installer closes the launch gap
- `ARCHITECTURE.md`, `BUILD_LOG.md` — design + honest status
