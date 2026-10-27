"""Shared voice daemon: ``python -m glados_voice.daemon``.

Binds a localhost port first (so a second copy exits immediately), then loads the
models and serves /speak, /stop and /status. Exits after GLADOS_IDLE_SECONDS
(default 600) without a request or speech, which unloads the models.

Env: GLADOS_PORT (default 18765), GLADOS_IDLE_SECONDS, GLADOS_BACKEND.
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 18765
DEFAULT_IDLE_SECONDS = 600.0
SERVICE = "glados-voice"


def get_port() -> int:
    return int(os.environ.get("GLADOS_PORT", DEFAULT_PORT))


def get_idle_seconds() -> float:
    return float(os.environ.get("GLADOS_IDLE_SECONDS", DEFAULT_IDLE_SECONDS))


class State:
    def __init__(self) -> None:
        self.engine = None
        self.engine_created = threading.Event()
        self.last_active = time.monotonic()
        self.started = time.time()

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def load_engine(self) -> None:
        from .engine import VoiceEngine  # heavy import, after the port is bound

        self.engine = VoiceEngine().start()
        self.engine_created.set()


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}", flush=True)

        def _send(self, payload: dict, code: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def _status(self) -> dict:
            idle_in = max(0.0, get_idle_seconds() - (time.monotonic() - state.last_active))
            info = {"service": SERVICE, "pid": os.getpid(), "idle_shutdown_in_seconds": round(idle_in)}
            if state.engine_created.is_set():
                info.update(state.engine.status())
            else:
                info.update({"ready": False, "speaking": False})
            return info

        def do_GET(self):
            if self.path == "/status":
                self._send(self._status())
            else:
                self._send({"error": "not found"}, 404)

        def do_POST(self):
            try:
                if self.path == "/speak":
                    state.touch()
                    data = self._body()
                    if not state.engine_created.wait(60):
                        self._send({"error": "engine failed to start"}, 503)
                        return
                    accepted, retry_after = state.engine.try_speak(str(data.get("text", "")))
                    if not accepted:
                        self._send({"accepted": False, "retry_after_seconds": max(1, round(retry_after))})
                        return
                    if data.get("wait"):
                        state.engine.wait_idle()
                    state.touch()
                    self._send({"accepted": True, "waited": bool(data.get("wait"))})
                elif self.path == "/stop":
                    state.touch()
                    if state.engine_created.is_set():
                        state.engine.stop()
                    self._send({"stopped": True})
                else:
                    self._send({"error": "not found"}, 404)
            except Exception as e:
                self._send({"error": repr(e)}, 500)

    return Handler


def watch_idle(state: State, server: ThreadingHTTPServer) -> None:
    while True:
        time.sleep(1)
        engine = state.engine
        if engine is not None and not engine.wait_idle(0):
            state.touch()  # speech in progress counts as activity
        if time.monotonic() - state.last_active >= get_idle_seconds():
            print("Idle timeout reached, shutting down.", flush=True)
            server.shutdown()
            return


def main() -> int:
    state = State()
    try:
        server = ThreadingHTTPServer((HOST, get_port()), make_handler(state))
    except OSError as e:
        print(f"Port {get_port()} unavailable (another daemon running?): {e}", flush=True)
        return 1
    server.daemon_threads = True
    print(f"glados-voice daemon on {HOST}:{get_port()} (pid {os.getpid()})", flush=True)
    threading.Thread(target=state.load_engine, name="loader", daemon=True).start()
    threading.Thread(target=watch_idle, args=(state, server), name="idle", daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
