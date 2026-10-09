"""Real production-image proxy checks with a disposable slow HTTP upstream."""

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from urllib.parse import urlparse

_lock = Lock()
_active = _peak = _requests = 0
_ports = set()


class Probe(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        global _active, _peak, _requests
        with _lock:
            _ports.add(self.client_address[1])
            _requests += 1
            held = self.path == "/api/hold"
            if held:
                _active += 1
                _peak = max(_peak, _active)
        if held:
            time.sleep(6)
        with _lock:
            body = json.dumps({"requests": _requests, "connections": len(_ports),
                               "peak_active": _peak}).encode()
            if held:
                _active -= 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    request_queue_size = 512
    daemon_threads = True


def verify(base_url, capacity):
    import requests

    if urlparse(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Proxy probe may only target a disposable localhost proxy")
    session = requests.Session()
    session.trust_env = False
    replies = [session.get(base_url + "/api/probe", timeout=10).json() for _ in range(20)]
    assert replies[-1]["connections"] == 1, replies[-1]
    print({"reuse_requests": 20, "upstream_connections": 1}, flush=True)
    denied = Event()

    def hold(_):
        client = requests.Session()
        client.trust_env = False
        response = client.get(base_url + "/api/hold", timeout=20)
        if response.status_code == 503:
            assert response.json()["code"] == "SERVICE_BUSY"
            assert response.headers["Retry-After"] == "2"
            assert "no-store" in response.headers["Cache-Control"]
            denied.set()
        else:
            assert response.status_code == 200
            assert response.json()["peak_active"] <= capacity
        return response.status_code

    with ThreadPoolExecutor(max_workers=capacity + 40) as executor:
        futures = [executor.submit(hold, i) for i in range(capacity + 40)]
        assert denied.wait(timeout=5), "Burst did not reach the configured cap"
        for path in ("/api/v1/health/", "/api/v1/readiness/"):
            assert session.get(base_url + path, timeout=3).status_code == 200
        statuses = Counter(future.result() for future in futures)
    peak = session.get(base_url + "/api/probe", timeout=10).json()["peak_active"]
    assert peak == capacity, (peak, capacity)
    assert statuses[503] > 0
    print({"statuses": dict(statuses), "peak_upstream_requests": peak,
           "health_and_readiness_during_saturation": 200}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("serve", "verify"))
    parser.add_argument("--url", default="http://127.0.0.1:58086")
    parser.add_argument("--capacity", type=int, default=128)
    args = parser.parse_args()
    if args.mode == "serve":
        Server(("0.0.0.0", 8000), Probe).serve_forever()  # noqa: S104 - isolated Docker network
    else:
        verify(args.url.rstrip("/"), args.capacity)
