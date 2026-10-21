"""Deterministic local web content for tests (no internet needed).

Static files come from ``resources/site/``. Dynamic routes:

    /page?title=T&body=B          HTML page with that <title> (unique history/bookmark entries)
    /download?name=a.txt&size=N&type=text/plain   attachment download of N bytes
    /slow-download?name=big.bin&size=N&chunk=K&delay=S  streamed slowly (pause/resume/cancel)
    /redirect?to=/page?title=X    302 redirect
    /echo                         GET/POST -> JSON of query + form fields
    /upload                       POST multipart -> JSON {fields, files: [{field, name, size}]}
    /status?code=404              any HTTP status
    /basic-auth                   HTTP Basic auth, user "sbtest" / password "sbtest" (browser sign-in prompt)
    /delayed?ms=1500&text=Ready   page whose #late element appears after ms (wait examples)

    site = LocalSite(root).start();  site.url("/page", title="Hello")  ->  http://127.0.0.1:PORT/page?title=Hello
"""
from __future__ import annotations

import base64
import html
import json
import threading
import time
from email.parser import BytesParser
from email.policy import default as email_default
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


AUTH_USER = AUTH_PASSWORD = "sbtest"


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep test output clean
        pass

    def _qs(self) -> dict[str, str]:
        return {k: v[-1] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8", headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        q = self._qs()
        if route == "/page":
            title = html.escape(q.get("title", "Test page"))
            body = html.escape(q.get("body", f"Content of {q.get('title', 'Test page')}"))
            page = (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head>"
                    f"<body><h1 id='title'>{title}</h1><p id='body'>{body}</p>"
                    f"<a id='home' href='/index.html'>Home</a></body></html>")
            return self._send(200, page.encode())
        if route == "/download":
            name = q.get("name", "file.txt")
            size = int(q.get("size", "1024"))
            data = (b"sbtest-download-" * (size // 16 + 1))[:size]
            return self._send(200, data, q.get("type", "application/octet-stream"),
                              {"Content-Disposition": f'attachment; filename="{name}"'})
        if route == "/slow-download":
            return self._slow_download(q)
        if route == "/redirect":
            self.send_response(302)
            self.send_header("Location", q.get("to", "/index.html"))
            self.end_headers()
            return None
        if route == "/status":
            code = int(q.get("code", "404"))
            return self._send(code, f"<h1>Status {code}</h1>".encode())
        if route == "/echo":
            return self._send(200, json.dumps({"method": "GET", "query": q}).encode(), "application/json")
        if route == "/basic-auth":
            expected = "Basic " + base64.b64encode(f"{AUTH_USER}:{AUTH_PASSWORD}".encode()).decode()
            if self.headers.get("Authorization") != expected:
                return self._send(401, b"<h1>Authentication required</h1>",
                                  headers={"WWW-Authenticate": 'Basic realm="sbtest"'})
            return self._send(200, b"<!doctype html><title>Signed in</title><h1 id='title'>Signed in</h1>")
        if route == "/delayed":
            ms, text = int(q.get("ms", "1500")), html.escape(q.get("text", "Ready"))
            page = (f"<!doctype html><title>Delayed</title><h1>Delayed</h1><script>setTimeout(() => {{"
                    f"const p = document.createElement('p'); p.id = 'late'; p.textContent = '{text}';"
                    f"document.body.appendChild(p); }}, {ms});</script>")
            return self._send(200, page.encode())
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        if self.headers.get("Content-Type", "").startswith("multipart/form-data"):
            return self._multipart(self.rfile.read(length))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        return self._send(200, json.dumps({"method": "POST", "form": form, "query": self._qs()}).encode(),
                          "application/json")

    def _multipart(self, body: bytes) -> None:
        msg = BytesParser(policy=email_default).parsebytes(
            f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body)
        fields, uploaded = {}, []
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                uploaded.append({"field": name, "name": filename, "size": len(payload)})
            elif name:
                fields[name] = payload.decode("utf-8", "replace")
        return self._send(200, json.dumps({"method": "POST", "fields": fields, "files": uploaded}).encode(),
                          "application/json")

    def _slow_download(self, q: dict) -> None:
        name = q.get("name", "slow.bin")
        size = int(q.get("size", str(5 * 1024 * 1024)))
        chunk = int(q.get("chunk", "65536"))
        delay = float(q.get("delay", "0.2"))
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.end_headers()
        sent = 0
        try:
            while sent < size:
                n = min(chunk, size - sent)
                self.wfile.write(b"x" * n)
                self.wfile.flush()
                sent += n
                time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser cancelled / paused


class LocalSite:
    def __init__(self, root: Path, host: str = "127.0.0.1", port: int = 0) -> None:
        self.root = Path(root)
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> "LocalSite":
        handler = partial(_Handler, directory=str(self.root))
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def base(self) -> str:
        return f"http://{self.host}:{self.port}"

    def url(self, path: str = "/", **query) -> str:
        """``site.url("/page", title="A")`` -> full URL with encoded query."""
        if not path.startswith("/"):
            path = "/" + path
        return self.base + path + (("&" if "?" in path else "?") + urlencode(query) if query else "")

    def page(self, title: str, body: str | None = None) -> str:
        return self.url("/page", title=title, **({"body": body} if body else {}))

    def download(self, name: str, size: int = 1024, ctype: str = "application/octet-stream") -> str:
        return self.url("/download", name=name, size=size, type=ctype)

    def slow_download(self, name: str, size: int = 5 * 1024 * 1024, chunk: int = 65536, delay: float = 0.2) -> str:
        return self.url("/slow-download", name=name, size=size, chunk=chunk, delay=delay)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
