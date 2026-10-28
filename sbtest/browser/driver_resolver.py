"""Find a chromedriver that matches the browser's Chromium version.

Order:
1. ``browser.chromedriver`` from config/env/CLI (recommended: built from the fork itself)
2. ``drivers/<major>/chromedriver[.exe]`` already in the repo folder (offline machines)
3. Download from Chrome for Testing for the same Chromium *build* (x.y.BUILD), cached into
   ``drivers/<major>/``. Selenium Manager is not used for this on purpose: it would read the
   Samsung product version from the exe instead of the Chromium one.
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from sbtest.browser.version import major
from sbtest.config import ROOT
from sbtest.utils import log

EXE_NAME = "chromedriver.exe" if os.name == "nt" else "chromedriver"
CFT = "https://googlechromelabs.github.io/chrome-for-testing"


def cft_platform() -> str:
    machine = platform.machine().lower()
    if os.name == "nt":
        return "win64" if machine.endswith("64") else "win32"
    if platform.system() == "Darwin":
        return "mac-arm64" if machine in ("arm64", "aarch64") else "mac-x64"
    return "linux64"


_PROXY: str = ""  # set by resolve_chromedriver from config network.download_proxy


def _open(url: str, timeout: float):
    """urlopen honouring HTTPS_PROXY/HTTP_PROXY env vars, or an explicit proxy."""
    handlers = [urllib.request.ProxyHandler({"http": _PROXY, "https": _PROXY})] if _PROXY else []
    return urllib.request.build_opener(*handlers).open(url, timeout=timeout)


def _get_json(url: str) -> dict:
    with _open(url, 60) as r:
        return json.loads(r.read().decode("utf-8"))


def chromedriver_url(chromium_version: str, plat: str | None = None) -> tuple[str, str]:
    """(version, download url) of the Chrome for Testing chromedriver closest to ``chromium_version``:
    same build (x.y.BUILD) if available, else the latest of the milestone."""
    plat = plat or cft_platform()
    build = ".".join(chromium_version.split(".")[:3])
    candidates = []
    try:
        builds = _get_json(f"{CFT}/latest-patch-versions-per-build-with-downloads.json")["builds"]
        if build in builds:
            candidates.append(builds[build])
    except Exception as e:  # noqa: BLE001 - fall back to milestone list
        log.warning("CfT builds list failed: %s", e)
    milestones = _get_json(f"{CFT}/latest-versions-per-milestone-with-downloads.json")["milestones"]
    if str(major(chromium_version)) in milestones:
        candidates.append(milestones[str(major(chromium_version))])
    for c in candidates:
        for d in c.get("downloads", {}).get("chromedriver", []):
            if d["platform"] == plat:
                return c["version"], d["url"]
    raise RuntimeError(f"No chromedriver for Chromium {chromium_version} ({plat}) on Chrome for Testing")


def download_chromedriver(chromium_version: str, target_dir: Path) -> Path:
    version, url = chromedriver_url(chromium_version)
    log.info("Downloading chromedriver %s for Chromium %s: %s", version, chromium_version, url)
    with _open(url, 300) as r:
        data = r.read()
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        member = next(n for n in z.namelist() if n.endswith("/" + EXE_NAME) or n == EXE_NAME)
        out = target_dir / EXE_NAME
        out.write_bytes(z.read(member))
    out.chmod(out.stat().st_mode | stat.S_IEXEC)
    (target_dir / "VERSION").write_text(version)
    return out


def driver_version(path: str | Path) -> str | None:
    """``chromedriver --version`` -> "148.0.7778.97" (None when it cannot be read)."""
    try:
        out = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=15).stdout
    except Exception as e:  # noqa: BLE001
        log.warning("cannot run %s --version: %s", path, e)
        return None
    m = re.search(r"ChromeDriver (\d+(?:\.\d+){1,3})", out)
    return m.group(1) if m else None


def check_driver(path: str | Path, chromium_version: str | None, strict: bool) -> None:
    """Compare the driver major with the Chromium major ourselves, with a clear message.

    chromedriver's own check is switched off (``--disable-build-check``, see session) because it
    reads the DevTools ``Browser`` field, which holds the Samsung product version on some builds."""
    found = driver_version(path) if chromium_version else None
    if not found or major(found) == major(chromium_version):
        return
    msg = (f"chromedriver {path} is version {found} but the browser is Chromium {chromium_version}: "
           f"use a chromedriver {major(chromium_version)}")
    if strict:
        raise RuntimeError(msg + f" (delete {Path(path).parent} to download the right one)")
    log.warning(msg + " (configured driver kept - a driver built from the fork may number itself differently)")


def resolve_chromedriver(configured: str, chromium_version: str | None, drivers_dir: Path = ROOT / "drivers",
                         proxy: str = "") -> str:
    global _PROXY
    _PROXY = proxy or ""
    if configured:
        if not Path(configured).exists():
            raise FileNotFoundError(f"Configured chromedriver not found: {configured}")
        check_driver(configured, chromium_version, strict=False)
        return configured
    if not chromium_version:
        raise RuntimeError("Cannot resolve chromedriver: no chromium version and no configured driver")
    local = drivers_dir / str(major(chromium_version)) / EXE_NAME
    if local.exists():
        check_driver(local, chromium_version, strict=True)
        return str(local)
    try:
        return str(download_chromedriver(chromium_version, local.parent))
    except Exception as e:
        raise RuntimeError(
            f"Could not download chromedriver for Chromium {chromium_version} ({e}). Behind a proxy set "
            f"HTTPS_PROXY or network.download_proxy, or put the driver at {local} / set browser.chromedriver."
        ) from e
