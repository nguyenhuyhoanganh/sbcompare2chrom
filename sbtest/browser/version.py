"""Detect which Chromium version a (forked) browser build is based on.

The Samsung Internet product version differs from its Chromium base, and chromedriver
must match the Chromium major. We start the exe once with remote debugging, read
``/json/version`` and take the ``Chrome/x.y.z.w`` token. The result is cached per exe
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


def _cache_key(exe: Path) -> str:
    st = exe.stat()
    return f"{exe.resolve()}|{st.st_size}|{int(st.st_mtime)}"


def read_devtools_version(port: int, host: str = "127.0.0.1", timeout: float = 5) -> dict:
    no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via company proxy
    with no_proxy.open(f"http://{host}:{port}/json/version", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_devtools_port(user_data_dir: Path, timeout: float = 30) -> int:
    """Chromium writes the chosen port to <user-data-dir>/DevToolsActivePort."""
    f = user_data_dir / "DevToolsActivePort"
    end = time.time() + timeout
    while time.time() < end:
        if f.exists():
            first = f.read_text(errors="ignore").splitlines()[:1]
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
        version = parse_chromium_version(info.get("Browser", ""), info.get("User-Agent", ""))
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
