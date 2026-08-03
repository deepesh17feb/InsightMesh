#!/usr/bin/env python3
"""Local authenticated reverse proxy for Cloud Run.

Proxies http://localhost:8088 to https://insightmesh-app-704907518971.us-east1.run.app
attaching the user's gcloud identity token via X-Serverless-Authorization and preserving
client session cookies, SSE streams, and LibreChat JWT Authorization headers.
"""
from __future__ import annotations

import http.server
import socketserver
import subprocess
import urllib.error
import urllib.request
import sys
import time

TARGET_URL = "https://insightmesh-ui-704907518971.us-east1.run.app"
PORT = 8088

_cached_token = ""
_token_expiry = 0


def get_auth_token() -> str:
    global _cached_token, _token_expiry
    now = time.time()
    if not _cached_token or now > _token_expiry:
        try:
            res = subprocess.run(
                ["gcloud", "auth", "print-identity-token"],
                capture_output=True,
                text=True,
                check=True,
            )
            _cached_token = res.stdout.strip()
            _token_expiry = now + 1800  # cache for 30 minutes
        except Exception as e:
            print(f"[Proxy] Error getting auth token: {e}", file=sys.stderr)
    return _cached_token


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self._forward_request("GET")

    def do_POST(self):
        self._forward_request("POST")

    def do_PUT(self):
        self._forward_request("PUT")

    def do_DELETE(self):
        self._forward_request("DELETE")

    def do_HEAD(self):
        self._forward_request("HEAD")

    def do_OPTIONS(self):
        self._forward_request("OPTIONS")

    def do_PATCH(self):
        self._forward_request("PATCH")

    def _forward_request(self, method: str):
        token = get_auth_token()
        url = f"{TARGET_URL}{self.path}"

        headers = {}
        # Forward incoming request headers from client browser
        for k, v in self.headers.items():
            if k.lower() not in ("host", "accept-encoding"):
                headers[k] = v

        # Google Cloud Run IAM authentication header
        # Uses X-Serverless-Authorization so LibreChat's own Authorization/JWT header is unaffected
        headers["X-Serverless-Authorization"] = f"Bearer {token}"

        body = None
        if "Content-Length" in self.headers:
            try:
                content_len = int(self.headers["Content-Length"])
                body = self.rfile.read(content_len)
            except Exception:
                body = None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                # Forward all response headers except hop-by-hop and Set-Cookie
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length", "set-cookie"):
                        self.send_header(k, v)

                # Forward all Set-Cookie headers individually
                set_cookies = resp.headers.get_all("Set-Cookie") or []
                for cookie in set_cookies:
                    # Remove Secure attribute if accessing over plain HTTP localhost
                    modified_cookie = cookie
                    self.send_header("Set-Cookie", modified_cookie)

                content = resp.read()
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding", "content-length", "set-cookie"):
                    self.send_header(k, v)

            set_cookies = e.headers.get_all("Set-Cookie") or []
            for cookie in set_cookies:
                self.send_header("Set-Cookie", cookie)

            content = e.read()
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            msg = f"Bad Gateway: {e}".encode("utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, format, *args):
        pass


def run(port: int = PORT):
    class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("0.0.0.0", port), ProxyHandler)
    print(f"==============================================================================")
    print(f"  InsightMesh Cloud Run Authenticated Proxy Running!")
    print(f"  Local Browser URL: http://localhost:{port}")
    print(f"  Upstream Cloud Run: {TARGET_URL}")
    print(f"==============================================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run(p)
