"""Detect which Chromium version a (forked) browser build is based on.

The Samsung Internet product version differs from its Chromium base, and chromedriver
must match the Chromium major. We start the exe once with remote debugging, read
``/json/version`` and take the ``Chrome/x.y.z.w`` token of ``Browser``, or of the
User-Agent when ``Browser`` holds the product version (``chromium_version_from``). The result is cached per exe
(path + size + mtime) so it costs a few seconds only after a new build is dropped in.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from sbtest.utils import kill_tree, log

CHROME_TOKEN = re.compile(r"(?:Chrome|Chromium|HeadlessChrome)/(\d+\.\d+\.\d+\.\d+)")


def parse_chromium_version(*texts: str) -> str | None:
    """Return the first ``Chrome/x.y.z.w`` version found in the given strings."""
    for t in texts:
        m = CHROME_TOKEN.search(t or "")
        if m:
            return m.group(1)
    return None


def major(version: str) -> int:
    return int(version.split(".")[0])


def chromium_version_from(info: dict) -> str | None:
    """Chromium version from DevTools ``/json/version``.

    ``Browser`` normally holds the full Chromium version ("Chrome/148.0.7778.217"), but some
    Samsung builds put the product version there ("Chrome/31.0.1.21" on a Chromium 157 build).
    The User-Agent keeps the real Chromium major, reduced to "Chrome/157.0.0.0" (UA reduction):
    when the two majors differ, trust the User-Agent (the driver lookup falls back from the
    exact build to the latest driver of that major)."""
    browser = parse_chromium_version(info.get("Browser", ""))
    ua = parse_chromium_version(info.get("User-Agent", ""))
    if browser and ua and major(browser) != major(ua):
        log.warning("DevTools Browser field says %s but the User-Agent says Chrome %s: using the "
                    "User-Agent (the Browser field holds the product version)", browser, ua)
        return ua
    return browser or ua


# bump when the detection changes, so versions cached by an older rule are probed again
_CACHE_VERSION = 2


def _cache_key(exe: Path) -> str:
    st = exe.stat()
    return f"v{_CACHE_VERSION}|{exe.resolve()}|{st.st_size}|{int(st.st_mtime)}"


def read_devtools_version(port: int, host: str = "127.0.0.1", timeout: float = 5) -> dict:
    no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via company proxy
    with no_proxy.open(f"http://{host}:{port}/json/version", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_devtools_port(user_data_dir: Path, timeout: float = 30) -> int:
    """Chromium writes the chosen port to <user-data-dir>/DevToolsActivePort."""
    f = user_data_dir / "DevToolsActivePort"
    end = time.time() + timeout
    while time.time() < end:
        try:
            first = f.read_text(errors="ignore").splitlines()[:1] if f.exists() else []
        except OSError:   # the browser holds the file while it writes it (Windows: Permission denied)
            first = []
        if first and first[0].strip().isdigit():
            return int(first[0])
        time.sleep(0.2)
    raise TimeoutError(f"Browser did not write {f} within {timeout}s")


def probe_version(exe: Path, extra_args: list[str] | None = None, timeout: float = 40) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="sb_probe_"))
    args = [
        str(exe),
        f"--user-data-dir={tmp}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-minimized",
        *(extra_args or []),
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        port = wait_devtools_port(tmp, timeout)
        info = read_devtools_version(port)
        log.info("DevTools /json/version: %s", info)
        version = chromium_version_from(info)
        if not version:
            raise RuntimeError(f"No Chrome/x.y.z.w token in DevTools version info: {info}")
        return version
    finally:
        kill_tree(proc.pid)
        shutil.rmtree(tmp, ignore_errors=True)


def detect_chromium_version(exe: str | Path, cache_dir: Path, extra_args: list[str] | None = None) -> str:
    exe = Path(exe)
    cache_file = cache_dir / "chromium_version.json"
    cache: dict = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except ValueError:
            cache = {}
    key = _cache_key(exe)
    if key in cache:
        return cache[key]
    version = probe_version(exe, extra_args)
    cache[key] = version
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=2))
    log.info("Detected Chromium %s for %s", version, exe)
    return version
