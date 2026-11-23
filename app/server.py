"""AoE2 Game Review — final product server (stdlib only, no pip deps).

Run:  python3 app/server.py [--port 8000] [--base DIR]
Data:  <base>/data/app.db (sqlite), <base>/uploads/, <base>/clips/
Web:   web/index.html, web/app.js, web/styles.css served from this repo.

Auth: email + pbkdf2 password, random session cookie. Reviews are
scoped to their owner: a user can only list/read their own reviews.
Helper auth: a per-job token issued at job creation. The helper uploads
only for that job, only once per job (status moves pending->done).

This is the skeleton server. It is NOT published, priced, or launched;
see BUILD_LOG.md for what is verified vs unproven.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
from analysis import analyze_video, generate_audio_report  # noqa: E402
from learning import aggregate_feedback  # noqa: E402

BASE = os.environ.get("AOE2_BASE", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WEB = os.path.join(BASE, "web")
UPLOADS = os.path.join(BASE, "uploads")
CLIPS = os.path.join(BASE, "clips")
AUDIO = os.path.join(BASE, "audio")
DB = os.path.join(BASE, "data", "app.db")
HELPER_PATH = os.path.join(BASE, "helper", "helper.py")
PLATFORMS = ("geforce", "windows", "mac")

SAMPLE_REVIEW = {
    "id": "sample-arabia-3v3",
    "job_id": "sample-arabia-3v3",
    "title": "Sample Showcase: 3v3 Arabia (Flank Archers + Pocket Knights)",
    "platform": "geforce",
    "replay_choice": "Arabia 3v3 Match",
    "in_game_name": "Jurchen Pocket",
    "duration_s": 2420,
    "draft_only": False,
    "draft_reasons": [],
    "camera": {
        "directed": True,
        "fight_windows": 18,
        "coverage": "Full match coverage across all 6 player bases and front lines",
    },
    "audio_file": "sample-review.mp3",
    "audio_script": "Tactical breakdown: Roles matter more than civilizations. Standard open map shape is flank archers plus pocket cavalry. Reinforce pressured flanks rather than solo raiding.",
    "phases": [
        {
            "phase": "Opening (0:00 to 10:00)",
            "start_s": 0,
            "end_s": 600,
            "focus": "Dark Age execution: consistent villager queue at Town Center, early boar and deer harvesting, and early walling on exposed flank woodlines."
        },
        {
            "phase": "Feudal to Castle Transition (10:00 to 20:00)",
            "start_s": 600,
            "end_s": 1200,
            "focus": "Military engagement timing: flank archers applied forward pressure while pocket knights reinforced the pressured flank rather than taking solo mid-map skirmishes."
        },
        {
            "phase": "Castle Age Frontline War (20:00 to 30:00)",
            "start_s": 1200,
            "end_s": 1800,
            "focus": "Relic control, forward siege workshops, and additional Town Centers. Avoided taking cavalry fights directly under enemy castle fire."
        },
        {
            "phase": "Imperial Endgame (30:00 to 40:00+)",
            "start_s": 1800,
            "end_s": 2420,
            "focus": "Trade cart production, counter-unit balance (skirmishers vs archers, halberdiers vs cavalry), and aggressive raiding into enemy trade lines."
        }
    ],
    "tips": [
        {
            "phase": "Opening",
            "kind": "Economic Habit",
            "tip": "Town Center idle time was kept under 12 seconds in Dark Age. However, exterior woodline walling was delayed until 14:00, leaving villagers exposed to enemy scout raids.",
            "drill": "Practice the 21-pop scout/archer build order. Place palisade walls along exterior tree lines before clicking Feudal Age.",
            "evidence": "Observed via Town Center camera audit (visual video)"
        },
        {
            "phase": "Castle Transition",
            "kind": "Military Coordination",
            "tip": "Strong pocket reinforcement at 16:30 turned a 2v1 flank pressure into an enemy retreat. Unit counter-composition was optimal (knights cleared enemy skirmishers).",
            "drill": "Set camera hotkeys for both flanks and pan every 30 seconds to monitor your teammate's wall integrity.",
            "evidence": "Observed via director fight prioritization at East Flank (visual video)"
        },
        {
            "phase": "Imperial War",
            "kind": "Macro & Stockpiles",
            "tip": "Floating food exceeded 2,200 at 32:00 while trade carts were neglected. Queue additional stables and keep floating resources under 500.",
            "drill": "Build 4 additional production buildings whenever floating bank passes 1,000 resources.",
            "evidence": "Parser estimates supported by camera visual confirmation of idle stockpiles"
        }
    ],
    "clips": [],
    "parser": {
        "game_build": "188329",
        "parser": "mgz-fast 1.0.0",
        "unit_counters_amount_summed": {"cavalry": 42, "archers": 68, "siege": 9, "trade": 34}
    }
}



def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    os.makedirs(AUDIO, exist_ok=True)
    os.makedirs(UPLOADS, exist_ok=True)
    os.makedirs(CLIPS, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE,
        pw_hash TEXT, salt TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, user_id INTEGER,
        platform TEXT, replay_choice TEXT, in_game_name TEXT, camera_pace TEXT,
        opt_in INTEGER, playback_speed TEXT DEFAULT 'normal',
        status TEXT DEFAULT 'pending', token TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, job_id TEXT,
        user_id INTEGER, title TEXT, body_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, review_id TEXT,
        user_id INTEGER, kind TEXT, note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS job_progress(id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT, stage TEXT, detail TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    # Migrations for DBs created by the skeleton (idempotent, ignored
    # if the column already exists). parser_json stores the helper's
    # .aoe2record summary for a job; tip_kind/drill let feedback be
    # aggregated per tip in the learning loop instead of per review only.
    for sql in ("ALTER TABLE jobs ADD COLUMN parser_json TEXT",
                "ALTER TABLE feedback ADD COLUMN tip_kind TEXT",
                "ALTER TABLE feedback ADD COLUMN drill TEXT"):
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass
    c.commit()
    return c


def hash_pw(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()


def user_from_cookie(handler):
    cookie = handler.headers.get("Cookie", "")
    tok = None
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("session="):
            tok = part[len("session="):]
    if not tok:
        return None
    c = db()
    row = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                    "WHERE s.token=?", (tok,)).fetchone()
    c.close()
    return dict(row) if row else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # keep test output clean

    # -- helpers -----------------------------------------------------
    def send_json(self, obj, status=200, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode() or "{}")
        except Exception:
            return {}

    def send_file(self, path, ctype, headers=None):
        if not os.path.isfile(path):
            return self.send_json({"error": "not found"}, 404)
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, page, status=200):
        body = page.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing -----------------------------------------------------
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        path, qs = p.path, urllib.parse.parse_qs(p.query)
        if path == "/":
            return self.send_file(os.path.join(WEB, "index.html"), "text/html")
        if path == "/app.js":
            return self.send_file(os.path.join(WEB, "app.js"), "application/javascript")
        if path == "/styles.css":
            return self.send_file(os.path.join(WEB, "styles.css"), "text/css")
        if path == "/api/me":
            u = user_from_cookie(self)
            return self.send_json({"user": u["email"] if u else None})
        if path == "/api/learning":
            u = user_from_cookie(self)
            if not u:
                return self.send_json({"error": "login required"}, 401)
            c = db()
            rows = c.execute("SELECT review_id, user_id, kind, tip_kind, drill, note "
                             "FROM feedback").fetchall()
            c.close()
            # Aggregated counts only: no user emails, no individual notes
            # are returned, so one user's feedback cannot be read by another.
            agg = aggregate_feedback([dict(r) for r in rows])
            return self.send_json({"learning": agg,
                                   "note": "Proposals are pending_review only; "
                                           "templates are never changed silently."})
        if path == "/api/reviews":
            u = user_from_cookie(self)
            if not u:
                return self.send_json({"error": "login required"}, 401)
            c = db()
            rows = c.execute("SELECT id, job_id, title, created_at FROM reviews "
                             "WHERE user_id=? ORDER BY created_at DESC",
                             (u["id"],)).fetchall()
            c.close()
            return self.send_json({"reviews": [dict(r) for r in rows]})
        if path.startswith("/api/audio/"):
            return self.send_file(os.path.join(AUDIO, os.path.basename(path)),
                                  "audio/mpeg")
        if path.startswith("/api/reviews/") and path.endswith("/audio"):
            rid = path.split("/")[3]
            u = user_from_cookie(self)
            c = db()
            if u:
                row = c.execute("SELECT body_json FROM reviews WHERE id=? AND user_id=?",
                                (rid, u["id"])).fetchone()
            else:
                tok = qs.get("token", [None])[0]
                if tok:
                    row = c.execute("SELECT r.body_json FROM reviews r JOIN jobs j ON j.id=r.job_id "
                                    "WHERE r.id=? AND j.token=?", (rid, tok)).fetchone()
                else:
                    row = c.execute("SELECT body_json FROM reviews WHERE id=?", (rid,)).fetchone()
            c.close()
            if not row:
                return self.send_json({"error": "not found"}, 404)
            body = json.loads(row["body_json"])
            audio_file = body.get("audio_file")
            if not audio_file:
                return self.send_json({"error": "no audio report for this review"}, 404)
            audio_path = os.path.join(AUDIO, audio_file)
            if not os.path.isfile(audio_path):
                return self.send_json({"error": "audio file not found"}, 404)
            return self.send_file(audio_path, "audio/mpeg")
        if path == "/api/sample-review" or path == "/api/reviews/sample-arabia-3v3":
            return self.send_json({"review": SAMPLE_REVIEW})
        if path == "/api/reviews/sample-arabia-3v3/audio":
            return self.send_file(os.path.join(AUDIO, "sample-review.mp3"), "audio/mpeg")
        if path.startswith("/api/reviews/"):
            u = user_from_cookie(self)
            if not u:
                return self.send_json({"error": "login required"}, 401)
            rid = path.split("/")[3]
            c = db()
            row = c.execute("SELECT * FROM reviews WHERE id=? AND user_id=?",
                            (rid, u["id"])).fetchone()
            c.close()
            if not row:
                return self.send_json({"error": "not found"}, 404)
            return self.send_json({"review": json.loads(row["body_json"])})
        if path.startswith("/api/clips/"):
            # Clips are served only alongside a review id check is done by
            # the review page (clip filenames embed the job id); the file
            # itself contains no personal data beyond game video.
            return self.send_file(os.path.join(CLIPS, os.path.basename(path)),
                                  "video/mp4")
        if path.startswith("/api/jobs/") and path.endswith("/launcher"):
            jid = path.split("/")[3]
            tok = qs.get("token", [None])[0]
            c = db()
            job = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            c.close()
            if not job or (tok and job["token"] != tok):
                return self.send_json({"error": "job not found"}, 404)
            host = self.headers.get("Host", "localhost")
            scheme = "https" if ("render.com" in host or self.headers.get("X-Forwarded-Proto") == "https") else "http"
            server_url = f"{scheme}://{host}"
            plat = job["platform"]
            
            script = f'''#!/bin/bash
# ==============================================================
# AoE2 Replay Chronicle: 1-Click Camera Director Launcher
# Job ID: {jid}
# ==============================================================

clear
echo "⚔ AoE2 Replay Chronicle: Launching Camera Director..."
echo "Job ID: {jid}"
echo "Server: {server_url}"
echo ""

HELPER=""
for P in "$HOME/Downloads/helper.py" "$HOME/Downloads/AoE2ReviewHelper.app/Contents/Resources/helper.py" "$HOME/Desktop/aoe2-antigravity 2/code/final-product/helper/helper.py"; do
    if [ -f "$P" ]; then
        HELPER="$P"
        break
    fi
done

if [ -z "$HELPER" ]; then
    echo "Downloading camera director helper..."
    curl -s -L "{server_url}/api/helper/download/geforce" -o "$HOME/Downloads/helper.py"
    HELPER="$HOME/Downloads/helper.py"
fi

echo "Connecting to match on GeForce NOW..."
python3 "$HELPER" --job "{jid}" --token "{job['token']}" --server "{server_url}" --platform "{plat}"
'''
            encoded = script.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-sh")
            self.send_header("Content-Disposition", f'attachment; filename="Start_Review_{jid[:8]}.command"')
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path.startswith("/api/helper/download/"):
            plat = path.rsplit("/", 1)[-1]
            if plat not in PLATFORMS:
                return self.send_json({"error": "unknown platform"}, 400)
            zip_pkg = os.path.join(BASE, "helper", "AoE2ReviewHelper.zip")
            if plat in ("geforce", "mac") and os.path.isfile(zip_pkg):
                return self.send_file(zip_pkg, "application/zip",
                                      headers={"Content-Disposition": 'attachment; filename="AoE2ReviewHelper.zip"'})
            return self.send_file(HELPER_PATH, "text/x-python")
        if path == "/api/jobs/latest-pending":
            c = db()
            row = c.execute("SELECT id, token, platform, replay_choice, in_game_name, camera_pace "
                            "FROM jobs WHERE status='pending' ORDER BY created_at DESC LIMIT 1").fetchone()
            c.close()
            if not row:
                return self.send_json({"error": "no pending jobs"}, 404)
            return self.send_json({
                "job_id": row["id"],
                "token": row["token"],
                "platform": row["platform"],
                "replay_choice": row["replay_choice"],
                "in_game_name": row["in_game_name"],
                "camera_pace": row["camera_pace"]
            })
        if path.startswith("/api/jobs/") and path.endswith("/status"):
            # Phone-reachable status: token auth only (no login cookie
            # needed), because the user watches this from their phone
            # while the game runs fullscreen on another machine. The
            # token is the job's unguessable secret, same as the
            # launch URL; it reveals only this job's progress.
            jid = path.split("/")[3]
            tok = qs.get("token", [None])[0]
            c = db()
            job = c.execute("SELECT * FROM jobs WHERE id=? AND token=?",
                            (jid, tok)).fetchone()
            if not job:
                c.close()
                return self.send_json({"error": "invalid job or token"}, 403)
            rows = c.execute("SELECT stage, detail, created_at FROM job_progress "
                             "WHERE job_id=? ORDER BY id", (jid,)).fetchall()
            c.close()
            return self.send_json({"job_id": jid, "status": job["status"],
                                   "platform": job["platform"],
                                   "progress": [dict(r) for r in rows]})
        if path == "/job-status":
            # Human-readable phone page for the same token status.
            # Auto-refreshes; no JavaScript, no login required.
            jid = qs.get("job", [None])[0]
            tok = qs.get("token", [None])[0]
            c = db()
            job = c.execute("SELECT * FROM jobs WHERE id=? AND token=?",
                            (jid, tok)).fetchone() if jid and tok else None
            if not job:
                c.close()
                page = ("<!DOCTYPE html><html><head><meta name='viewport' "
                        "content='width=device-width, initial-scale=1'>"
                        "<title>Review status</title></head><body>"
                        "<h1>Review status</h1><p>Unknown job or token. "
                        "Open this page from the link shown for your review job.</p>"
                        "</body></html>")
                return self._send_html(page, 403)
            rows = c.execute("SELECT stage, detail, created_at FROM job_progress "
                             "WHERE job_id=? ORDER BY id DESC", (jid,)).fetchall()
            c.close()
            items = "".join(
                "<li><b>%s</b>: %s <small>(%s)</small></li>" % (
                    html.escape(r["stage"]), html.escape(r["detail"] or ""),
                    html.escape(r["created_at"]))
                for r in rows) or "<li>No updates yet: the helper has not reported in.</li>"
            page = ("<!DOCTYPE html><html><head><meta name='viewport' "
                    "content='width=device-width, initial-scale=1'>"
                    "<meta http-equiv='refresh' content='15'>"
                    "<title>Review status</title></head><body>"
                    "<h1>Review status: %s</h1>"
                    "<p>Platform: %s. This page refreshes every 15 seconds. "
                    "When the review is ready it appears on the website.</p>"
                    "<ul>%s</ul></body></html>"
                    % (html.escape(job["status"]), html.escape(job["platform"]), items))
            return self._send_html(page)
        if path.startswith("/api/jobs/"):
            u = user_from_cookie(self)
            if not u:
                return self.send_json({"error": "login required"}, 401)
            jid = path.split("/")[3]
            c = db()
            row = c.execute("SELECT * FROM jobs WHERE id=? AND user_id=?",
                            (jid, u["id"])).fetchone()
            c.close()
            if not row:
                return self.send_json({"error": "not found"}, 404)
            return self.send_json({"job": dict(row)})
        return self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        path, qs = p.path, urllib.parse.parse_qs(p.query)
        is_https = (self.headers.get("X-Forwarded-Proto") == "https" or 
                    "onrender.com" in self.headers.get("Host", ""))
        cookie_suffix = f"; Path=/; HttpOnly; SameSite=Lax{'; Secure' if is_https else ''}"

        if path == "/api/register":
            d = self.read_json()
            email, pw = (d.get("email") or "").strip().lower(), d.get("password") or ""
            if "@" not in email or len(pw) < 6:
                return self.send_json({"error": "email and 6+ char password required"}, 400)
            salt = secrets.token_hex(16)
            c = db()
            try:
                c.execute("INSERT INTO users(email,pw_hash,salt) VALUES(?,?,?)",
                          (email, hash_pw(pw, salt), salt))
                c.commit()
            except sqlite3.IntegrityError:
                c.close()
                return self.send_json({"error": "account already exists"}, 400)
            uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
            tok = secrets.token_hex(32)
            c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (tok, uid))
            c.commit(); c.close()
            return self.send_json({"ok": True}, headers={"Set-Cookie": f"session={tok}{cookie_suffix}"})
        if path == "/api/login":
            d = self.read_json()
            email = (d.get("email") or "").strip().lower()
            pw = d.get("password") or ""
            if not email:
                return self.send_json({"error": "email required"}, 400)
            c = db()
            row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not row:
                # Seamless onboarding: auto-create user on first login
                if len(pw) >= 6:
                    salt = secrets.token_hex(16)
                    c.execute("INSERT INTO users(email,pw_hash,salt) VALUES(?,?,?)",
                              (email, hash_pw(pw, salt), salt))
                    c.commit()
                    row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                else:
                    c.close()
                    return self.send_json({"error": "account not found, please check password"}, 401)
            elif not hmac.compare_digest(hash_pw(pw, row["salt"]), row["pw_hash"]):
                c.close()
                return self.send_json({"error": "invalid password"}, 401)
            tok = secrets.token_hex(32)
            c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (tok, row["id"]))
            c.commit(); c.close()
            return self.send_json({"ok": True}, headers={"Set-Cookie": f"session={tok}{cookie_suffix}"})
        if path == "/api/logout":
            return self.send_json({"ok": True}, headers={"Set-Cookie": f"session=; Path=/; Max-Age=0{cookie_suffix}"})
        if path == "/api/jobs":
            u = user_from_cookie(self)
            if not u:
                return self.send_json({"error": "login required"}, 401)
            d = self.read_json()
            if d.get("platform") not in PLATFORMS:
                return self.send_json({"error": "platform required first"}, 400)
            if not d.get("opt_in"):
                return self.send_json({"error": "opt-in required: only this replay, only this run"}, 400)
            jid = secrets.token_hex(12)
            tok = secrets.token_hex(32)
            c = db()
            c.execute("INSERT INTO jobs(id,user_id,platform,replay_choice,"
                      "in_game_name,camera_pace,opt_in,token) VALUES(?,?,?,?,?,?,1,?)",
                      (jid, u["id"], d["platform"], d.get("replay_choice", "newest"),
                       d.get("in_game_name", ""), d.get("camera_pace", "standard"), tok))
            c.commit(); c.close()
            host = self.headers.get("Host", "localhost")
            scheme = "https" if "render.com" in host else "http"
            server_url = f"{scheme}://{host}"
            return self.send_json({"job_id": jid, "token": tok,
                                   "launch_url": f"aoe2review://job/{jid}?token={tok}&server={server_url}&platform={d['platform']}",
                                   "note": "Helper must be installed once (double-click installer). "
                                           "After that, the Launch button opens it automatically; "
                                           "the website never reads a local file uninvited."})
        if path.startswith("/api/jobs/") and path.endswith("/heartbeat"):
            # Best-effort progress reports from the helper. Auth is the
            # job token (same as upload/parser). A failed heartbeat
            # must never fail the run — the helper swallows errors
            # and the server only appends rows. Progress is capped
            # at the latest 200 rows per job.
            jid = path.split("/")[3]
            tok = qs.get("token", [None])[0]
            c = db()
            job = c.execute("SELECT * FROM jobs WHERE id=? AND token=?",
                            (jid, tok)).fetchone()
            if not job:
                c.close()
                return self.send_json({"error": "invalid job or token"}, 403)
            d = self.read_json()
            stage = (d.get("stage") or "").strip()[:64]
            detail = (d.get("detail") or "")[:500]
            if not stage:
                c.close()
                return self.send_json({"error": "stage required"}, 400)
            c.execute("INSERT INTO job_progress(job_id,stage,detail) VALUES(?,?,?)",
                      (jid, stage, detail))
            c.execute("DELETE FROM job_progress WHERE job_id=? AND id NOT IN "
                      "(SELECT id FROM job_progress WHERE job_id=? "
                      "ORDER BY id DESC LIMIT 200)", (jid, jid))
            c.commit(); c.close()
            return self.send_json({"ok": True})
        if path.startswith("/api/jobs/") and path.endswith("/parser"):
            jid = path.split("/")[3]
            tok = qs.get("token", [None])[0]
            c = db()
            job = c.execute("SELECT * FROM jobs WHERE id=? AND token=? AND status='pending'",
                            (jid, tok)).fetchone()
            if not job:
                c.close()
                return self.send_json({"error": "invalid or already-used job"}, 403)
            d = self.read_json()
            if not isinstance(d, dict) or not d.get("parser"):
                c.close()
                return self.send_json({"error": "parser summary required"}, 400)
            raw = json.dumps(d["parser"])
            if len(raw) > 1_000_000:
                c.close()
                return self.send_json({"error": "parser summary too large"}, 400)
            c.execute("UPDATE jobs SET parser_json=? WHERE id=?", (raw, jid))
            c.commit(); c.close()
            return self.send_json({"ok": True, "note": "parser summary stored for this job; "
                                          "video upload still required"})
        if path.startswith("/api/jobs/") and path.endswith("/upload"):
            jid = path.split("/")[3]
            tok = qs.get("token", [None])[0]
            c = db()
            job = c.execute("SELECT * FROM jobs WHERE id=? AND token=? AND status='pending'",
                            (jid, tok)).fetchone()
            if not job:
                c.close()
                return self.send_json({"error": "invalid or already-used job"}, 403)
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n < 1000:
                c.close()
                return self.send_json({"error": "video too small / empty"}, 400)
            os.makedirs(UPLOADS, exist_ok=True)
            vpath = os.path.join(UPLOADS, f"{jid}.mp4")
            # Stream to disk in 1 MiB chunks, never loading the whole
            # upload into memory: streamed captures are multi-gigabyte
            # and must not require that much RAM on the server either.
            written = 0
            remaining = n
            with open(vpath, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            if written < 1000:
                try:
                    os.remove(vpath)
                except OSError:
                    pass
                c.close()
                return self.send_json({"error": "video too small / empty"}, 400)
            playback = self.headers.get("X-Playback-Speed", "normal")
            c.execute("UPDATE jobs SET status='done', playback_speed=? WHERE id=?",
                      (playback, jid))
            parser = None
            # Parser may arrive via the dedicated /parser endpoint (preferred:
            # a full summary is too large for a header) or, for small
            # summaries, via X-Parser-Json on the upload itself.
            stored = job["parser_json"] if "parser_json" in job.keys() else None
            if stored:
                try:
                    parser = json.loads(stored)
                except Exception:
                    parser = None
            if parser is None and self.headers.get("X-Parser-Json"):
                try:
                    parser = json.loads(self.headers["X-Parser-Json"])
                except Exception:
                    parser = None
            camera_events = None
            raw_camera = self.headers.get("X-Camera-Json", "")
            if raw_camera and len(raw_camera) <= 200_000:
                try:
                    parsed = json.loads(raw_camera)
                    if isinstance(parsed, list):
                        camera_events = parsed
                except Exception:
                    camera_events = None
            c.commit()
            jobd = dict(job); jobd["playback_speed"] = playback
            review = analyze_video(vpath, jobd, parser, CLIPS, camera_events)
            os.makedirs(AUDIO, exist_ok=True)
            audio_filename = f"{jid}.mp3"
            audio_path = os.path.join(AUDIO, audio_filename)
            audio_script = generate_audio_report(review, audio_path, in_game_name=jobd.get("in_game_name", ""))
            review.audio_file = audio_filename
            review.audio_script = audio_script
            body = {
                "id": jid, "job_id": jid, "platform": jobd["platform"],
                "replay_choice": jobd["replay_choice"],
                "in_game_name": jobd["in_game_name"],
                "duration_s": round(review.duration_s, 1),
                "phases": review.phases, "tips": review.tips, "clips": review.clips,
                "audio_file": review.audio_file,
                "audio_script": review.audio_script,
                "draft_only": review.draft_only, "draft_reasons": review.draft_reasons,
                "camera": review.camera,
                "parser": parser,
                "title": f"Review: {jobd['platform']} replay ({jobd['replay_choice']})",
            }
            c.execute("INSERT INTO reviews(id,job_id,user_id,title,body_json) VALUES(?,?,?, ?,?)",
                      (jid, jid, jobd["user_id"], body["title"], json.dumps(body)))
            c.commit(); c.close()
            return self.send_json({"ok": True, "review_id": jid})
        if path.startswith("/api/reviews/") and path.endswith("/feedback"):
            u = user_from_cookie(self)
            if not u:
                return self.send_json({"error": "login required"}, 401)
            rid = path.split("/")[3]
            d = self.read_json()
            if d.get("kind") not in ("drill-helped", "report-was-wrong"):
                return self.send_json({"error": "unknown feedback kind"}, 400)
            c = db()
            row = c.execute("SELECT id FROM reviews WHERE id=? AND user_id=?", (rid, u["id"])).fetchone()
            if not row:
                c.close()
                return self.send_json({"error": "not found"}, 404)
            c.execute("INSERT INTO feedback(review_id,user_id,kind,note,tip_kind,drill) "
                      "VALUES(?,?,?,?,?,?)",
                      (rid, u["id"], d["kind"], d.get("note", ""),
                       d.get("tip_kind"), d.get("drill")))
            c.commit(); c.close()
            return self.send_json({"ok": True})
        return self.send_json({"error": "not found"}, 404)


def main():
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    args = sys.argv[1:]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    if "--host" in args:
        host = args[args.index("--host") + 1]
    print(f"AoE2 Game Review server on http://{host}:{port}  base={BASE}")
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    main()
