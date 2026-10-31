import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from glados_voice.daemon import HOST, State, make_handler


@pytest.fixture()
def port():
    server = ThreadingHTTPServer((HOST, 0), make_handler(State()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def call(port, method, path, headers=None, body=b"{}"):
    conn = http.client.HTTPConnection(HOST, port, timeout=5)
    conn.request(method, path, body=body if method == "POST" else None, headers=headers or {})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


JSON = {"Content-Type": "application/json"}


def test_status_allows_plain_local_request(port):
    status, data = call(port, "GET", "/status")
    assert status == 200 and data["service"] == "glados-voice"


def test_stop_allows_json_post(port):
    assert call(port, "POST", "/stop", JSON) == (200, {"stopped": True})


def test_post_rejects_text_plain(port):
    status, _ = call(port, "POST", "/stop", {"Content-Type": "text/plain"})
    assert status == 403


def test_post_rejects_missing_content_type(port):
    status, _ = call(port, "POST", "/stop")
    assert status == 403


@pytest.mark.parametrize("method,headers", [("GET", {}), ("POST", JSON)])
def test_rejects_origin_header(port, method, headers):
    status, _ = call(port, method, "/status" if method == "GET" else "/stop", {**headers, "Origin": "https://evil.example"})
    assert status == 403


@pytest.mark.parametrize("method,headers", [("GET", {}), ("POST", JSON)])
def test_rejects_foreign_host_header(port, method, headers):
    status, _ = call(port, method, "/status" if method == "GET" else "/stop", {**headers, "Host": "evil.example:18765"})
    assert status == 403


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2]", b'"text"'])
def test_speak_rejects_malformed_body_with_400(port, body):
    status, data = call(port, "POST", "/speak", JSON, body=body)
    assert status == 400 and "error" in data


def test_speak_rejects_oversized_body_with_400(port):
    status, _ = call(port, "POST", "/speak", {**JSON, "Content-Length": "999999"}, body=b"{}")
    assert status == 400


def test_accepts_localhost_host_header(port):
    status, _ = call(port, "GET", "/status", {"Host": f"localhost:{port}"})
    assert status == 200
