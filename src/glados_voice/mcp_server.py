"""MCP server (stdio) that speaks text in GLaDOS's voice.

This process is a thin proxy and starts instantly. The first ``speak`` call spawns
a shared daemon (glados_voice.daemon) that loads the models, serves every agent on
one audio device and exits after GLADOS_IDLE_SECONDS (default 600) of inactivity.

Run it with the ``glados-voice-mcp`` command.
Env: GLADOS_PORT, GLADOS_IDLE_SECONDS, GLADOS_BACKEND=cpu|cuda|auto (default cpu).
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from .daemon import HOST, SERVICE, get_port
from .persona import DELIVERY_RULES, PERSONA, REJECTION, TOOL_DESCRIPTION

LOG_PATH = Path(tempfile.gettempdir(), "glados_voice_daemon.log")
BASE_URL = f"http://{HOST}:{get_port()}"
DAEMON_START_TIMEOUT = 15.0

mcp = MCPServer(
    "glados-voice",
    instructions="Anything spoken through this server must be in character. Persona: " + PERSONA + " " + DELIVERY_RULES,
)


def _request(path: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # keep the daemon's {"error": ...} body
        try:
            return json.loads(e.read())
        except ValueError:
            raise e


def _daemon_status() -> dict | None:
    try:
        info = _request("/status", timeout=1.0)
    except (OSError, ValueError):
        return None
    return info if info.get("service") == SERVICE else None


def _spawn_daemon() -> None:
    kwargs = {}
    if sys.platform == "win32":
        # No DETACHED_PROCESS: it overrides CREATE_NO_WINDOW, and the venv's python.exe launcher
        # then opens a visible console for the real interpreter it starts.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    log = open(LOG_PATH, "ab")
    subprocess.Popen(
        [sys.executable, "-m", "glados_voice.daemon"],
        cwd=tempfile.gettempdir(),  # neutral cwd so nothing local shadows imports
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        **kwargs,
    )


def _ensure_daemon() -> None:
    if _daemon_status():
        return
    _spawn_daemon()
    deadline = time.monotonic() + DAEMON_START_TIMEOUT
    while time.monotonic() < deadline:
        if _daemon_status():
            return
        time.sleep(0.2)
    raise RuntimeError(f"voice daemon did not start; see {LOG_PATH}")


def _speak_blocking(text: str, wait: bool) -> str:
    _ensure_daemon()
    result = _request("/speak", {"text": text, "wait": wait}, timeout=600 if wait else 30)
    if "error" in result:
        return f"ERROR: {result['error']}"
    if not result["accepted"]:
        seconds = result["retry_after_seconds"]
        return f"BUSY: GLaDOS is already speaking. Retry in about {seconds} seconds."
    if wait:
        return "spoken"
    loading = result.get("load_eta_seconds", 0)
    return f"queued; voice models are loading, audio starts in about {loading} seconds" if loading else "queued"


def _stop_blocking() -> str:
    if not _daemon_status():
        return "nothing playing (voice daemon not running)"
    _request("/stop", {})
    return "stopped"


@mcp.tool(description=TOOL_DESCRIPTION)
async def speak(text: str, in_character: bool = True, wait: bool = False) -> str:
    try:
        if not text.strip():
            return await asyncio.to_thread(_stop_blocking)
        if not in_character:
            return REJECTION
        return await asyncio.to_thread(_speak_blocking, text, wait)
    except (OSError, RuntimeError, ValueError) as e:
        return f"ERROR: {e}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
