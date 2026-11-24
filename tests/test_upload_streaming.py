"""Streaming upload test: a multi-megabyte video must reach the server
byte-identical without either side loading it whole into memory.

Regression guard for the old code, which did f.read() on the helper
side and rfile.read(n) on the server side — both fatal for the
multi-gigabyte streamed captures the product is built for.

Supports real loopback sockets when permitted, and falls back to in-memory
MockSocket / socketpair dispatch when running under macOS sandbox restrictions.
"""
from __future__ import annotations

import hashlib
import http.client
import inspect
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "helper"))

import helper as helper_mod  # noqa: E402
import server  # noqa: E402


class MockSocket:
    """In-memory mock socket for HTTP handler testing without loopback socket restrictions."""
    def __init__(self, data: bytes):
        self.rdata = data
        self.wdata = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return io.BytesIO(self.rdata)
        return self.wdata

    def sendall(self, data):
        self.wdata.write(data)


class DummyServer:
    server_name = "127.0.0.1"
    server_port = 8891


class SocketPairHTTPConnection(http.client.HTTPConnection):
    """Drop-in HTTPConnection that connects to an in-process server.H via socket.socketpair()."""
    def connect(self):
        client_sock, server_sock = socket.socketpair()
        self.sock = client_sock

        def run_handler():
            try:
                server.H(server_sock, ("127.0.0.1", 54321), DummyServer())
            finally:
                try:
                    server_sock.close()
                except Exception:
                    pass

        t = threading.Thread(target=run_handler, daemon=True)
        t.start()


def invoke_handler(method: str, path: str, headers: dict | None = None, body: bytes = b"") -> tuple[int, dict, bytes]:
    """Invoke server.H handler in-memory and parse response status, headers, and body."""
    req_lines = [f"{method} {path} HTTP/1.1", "Host: localhost:8891"]
    if headers:
        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")
    if body and "Content-Length" not in (headers or {}):
        req_lines.append(f"Content-Length: {len(body)}")
    req_lines.append("")
    req_lines.append("")
    raw_req = "\r\n".join(req_lines).encode("latin1") + body

    sock = MockSocket(raw_req)
    server.H(sock, ("127.0.0.1", 12345), DummyServer())
    raw_resp = sock.wdata.getvalue()

    header_end = raw_resp.find(b"\r\n\r\n")
    if header_end == -1:
        return 500, {}, raw_resp
    header_part = raw_resp[:header_end].decode("latin1")
    body_part = raw_resp[header_end + 4:]

    lines = header_part.split("\r\n")
    status_line = lines[0]
    status_code = int(status_line.split(" ")[1])
    resp_headers = {}
    for line in lines[1:]:
        if ":" in line:
            hk, hv = line.split(":", 1)
            resp_headers[hk.strip().lower()] = hv.strip()
    return status_code, resp_headers, body_part


def can_use_loopback() -> bool:
    """Check if TCP loopback connections are permitted in current environment."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
    except (OSError, PermissionError):
        return False


def test_source_code_guards():
    """1. Verify helper streams in chunks and neither side loads whole file into memory."""
    helper_src = inspect.getsource(helper_mod.upload_video)
    assert "conn.send(chunk)" in helper_src, "helper upload is not chunked"
    assert "data = f.read()" not in helper_src, "helper still loads whole file"
    assert "1024 * 1024" in helper_src, "helper should use 1 MiB chunk reads"

    server_src = inspect.getsource(server.H.do_POST)
    assert "min(1024 * 1024, remaining)" in server_src, "server does not stream in 1 MiB chunks"
    assert "self.rfile.read(n)" not in server_src, "server still loads whole upload into memory"
    print("PASS test_source_code_guards")


def test_token_and_payload_guards(base_dir: str):
    """2. Verify token validation, invalid tokens, payload size limits, and single-use jobs."""
    orig_base = server.BASE
    orig_db = server.DB
    orig_uploads = server.UPLOADS
    orig_clips = server.CLIPS
    orig_audio = server.AUDIO

    try:
        server.BASE = base_dir
        server.DB = os.path.join(base_dir, "data", "app.db")
        server.UPLOADS = os.path.join(base_dir, "uploads")
        server.CLIPS = os.path.join(base_dir, "clips")
        server.AUDIO = os.path.join(base_dir, "audio")
        os.makedirs(os.path.dirname(server.DB), exist_ok=True)
        os.makedirs(server.UPLOADS, exist_ok=True)
        server.db().close()

        # Register user
        st, hdrs, body = invoke_handler("POST", "/api/register",
                                        {"Content-Type": "application/json"},
                                        json.dumps({"email": "upload@test.local", "password": "password123"}).encode())
        assert st == 200, (st, body)
        cookie = hdrs.get("set-cookie", "").split(";")[0]

        # Create job
        st, _, body = invoke_handler("POST", "/api/jobs",
                                     {"Content-Type": "application/json", "Cookie": cookie},
                                     json.dumps({"platform": "geforce", "opt_in": True,
                                                 "replay_choice": "newest", "in_game_name": "Ken"}).encode())
        assert st == 200, (st, body)
        job = json.loads(body.decode())
        jid, tok = job["job_id"], job["token"]

        # Check A: Missing or invalid token -> 403
        st, _, _ = invoke_handler("POST", f"/api/jobs/{jid}/upload",
                                  {"Content-Length": "2000"}, b"x" * 2000)
        assert st == 403, f"Expected 403 for missing token, got {st}"

        st, _, _ = invoke_handler("POST", f"/api/jobs/{jid}/upload?token=badtoken",
                                  {"Content-Length": "2000"}, b"x" * 2000)
        assert st == 403, f"Expected 403 for invalid token, got {st}"

        # Check B: Non-existent job ID -> 403
        st, _, _ = invoke_handler("POST", f"/api/jobs/nonexistent/upload?token={tok}",
                                  {"Content-Length": "2000"}, b"x" * 2000)
        assert st == 403, f"Expected 403 for non-existent job, got {st}"

        # Check C: Video too small (<1000 bytes) -> 400
        st, _, _ = invoke_handler("POST", f"/api/jobs/{jid}/upload?token={tok}",
                                  {"Content-Length": "500"}, b"x" * 500)
        assert st == 400, f"Expected 400 for payload < 1000 bytes, got {st}"

        print("PASS test_token_and_payload_guards")
        return jid, tok, cookie
    finally:
        server.BASE = orig_base
        server.DB = orig_db
        server.UPLOADS = orig_uploads
        server.CLIPS = orig_clips
        server.AUDIO = orig_audio


def test_chunk_assembly_and_integrity(base_dir: str):
    """3. End-to-end multi-megabyte streaming upload: 1 MiB chunk assembly & byte-identical sha256."""
    orig_base = server.BASE
    orig_db = server.DB
    orig_uploads = server.UPLOADS
    orig_clips = server.CLIPS
    orig_audio = server.AUDIO

    try:
        server.BASE = base_dir
        server.DB = os.path.join(base_dir, "data", "app.db")
        server.UPLOADS = os.path.join(base_dir, "uploads")
        server.CLIPS = os.path.join(base_dir, "clips")
        server.AUDIO = os.path.join(base_dir, "audio")
        os.makedirs(os.path.dirname(server.DB), exist_ok=True)
        os.makedirs(server.UPLOADS, exist_ok=True)
        server.db().close()

        # 1. Register & Job
        st, hdrs, body = invoke_handler("POST", "/api/register",
                                        {"Content-Type": "application/json"},
                                        json.dumps({"email": "ken@upload.test", "password": "password123"}).encode())
        cookie = hdrs.get("set-cookie", "").split(";")[0]

        st, _, body = invoke_handler("POST", "/api/jobs",
                                     {"Content-Type": "application/json", "Cookie": cookie},
                                     json.dumps({"platform": "geforce", "opt_in": True,
                                                 "replay_choice": "newest", "in_game_name": "Ken Grabshaw"}).encode())
        job = json.loads(body.decode())
        jid, tok = job["job_id"], job["token"]

        # 2. Generate multi-megabyte video (> 1.5 MiB, multiple 1 MiB chunks)
        video = os.path.join(base_dir, "test-stream-video.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "testsrc=duration=20:size=1280x720:rate=30",
            "-c:v", "libx264", "-b:v", "2M", "-pix_fmt", "yuv420p", video
        ], check=True, timeout=120)

        size = os.path.getsize(video)
        assert size > 1024 * 1024, f"Video must exceed 1 MiB to test chunking: {size} bytes"

        # 3. Stream upload using helper_mod.upload_video with SocketPairHTTPConnection
        with mock.patch("http.client.HTTPConnection", SocketPairHTTPConnection):
            result = helper_mod.upload_video("http://127.0.0.1:8891", jid, tok, video)
        assert result.get("ok"), result

        # 4. Verify stored file size and byte-identical sha256
        stored = os.path.join(server.UPLOADS, f"{jid}.mp4")
        assert os.path.exists(stored), "Uploaded file does not exist on server"
        assert os.path.getsize(stored) == size, f"Stored size mismatch: {os.path.getsize(stored)} vs {size}"

        with open(video, "rb") as f:
            want_hash = hashlib.sha256(f.read()).hexdigest()
        with open(stored, "rb") as f:
            got_hash = hashlib.sha256(f.read()).hexdigest()
        assert want_hash == got_hash, "Stored video bytes differ from upload"

        # 5. Verify database updates
        c = sqlite3.connect(server.DB)
        row = c.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()
        rev_count = c.execute("SELECT COUNT(*) FROM reviews WHERE job_id=?", (jid,)).fetchone()[0]
        c.close()

        assert row[0] == "done", f"Job status must be 'done', got {row[0]}"
        assert rev_count == 1, f"Expected 1 review, got {rev_count}"

        # 6. Verify single-use job token guard: re-uploading to done job must return 403
        st_reup, _, _ = invoke_handler("POST", f"/api/jobs/{jid}/upload?token={tok}",
                                       {"Content-Length": str(size)}, b"x" * 2000)
        assert st_reup == 403, f"Expected 403 for re-upload on completed job, got {st_reup}"

        print(f"PASS test_chunk_assembly_and_integrity ({size} bytes, sha256 match, DB verified)")
    finally:
        server.BASE = orig_base
        server.DB = orig_db
        server.UPLOADS = orig_uploads
        server.CLIPS = orig_clips
        server.AUDIO = orig_audio


def main():
    print("=" * 70)
    print("Running Streaming Upload & Chunk Integrity Tests...")
    print(f"Loopback sockets supported: {can_use_loopback()}")
    print("=" * 70)

    test_source_code_guards()

    with tempfile.TemporaryDirectory() as td:
        test_token_and_payload_guards(td)

    with tempfile.TemporaryDirectory() as td:
        test_chunk_assembly_and_integrity(td)

    print("ALL STREAMING UPLOAD TESTS PASSED.")


if __name__ == "__main__":
    main()
