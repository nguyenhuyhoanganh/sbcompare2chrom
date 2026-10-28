import json
import urllib.request

from sbtest.config import SITE_DIR
from sbtest.server import LocalSite
from sbtest.tools.coverage import automated_cases, doc_cases


def test_local_site_routes():
    s = LocalSite(SITE_DIR).start()
    try:
        with urllib.request.urlopen(s.page("Hello")) as r:
            assert b"<title>Hello</title>" in r.read()
        with urllib.request.urlopen(s.download("a.txt", 100)) as r:
            assert r.headers["Content-Disposition"] == 'attachment; filename="a.txt"'
            assert len(r.read()) == 100
        req = urllib.request.Request(s.url("/echo"), data=b"x=1&y=2", method="POST")
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read())["form"] == {"x": "1", "y": "2"}
        with urllib.request.urlopen(s.url("/index.html")) as r:
            assert b"sbtest local site" in r.read()
    finally:
        s.stop()


def test_every_automated_case_is_documented():
    docs, auto = doc_cases(), automated_cases()
    assert not set(auto) - set(docs), "case ids used in tests but missing from cases/"


def test_dropped_connections_are_not_printed(capsys):
    from sbtest.server.local_site import _Server

    server = _Server(("127.0.0.1", 0), lambda *a: None)
    try:
        for exc in (ConnectionAbortedError(10053, "aborted by the browser"), ValueError("a real bug")):
            try:
                raise exc
            except Exception:
                server.handle_error(None, ("127.0.0.1", 1))
    finally:
        server.server_close()
    err = capsys.readouterr().err
    assert "ConnectionAbortedError" not in err and "a real bug" in err
