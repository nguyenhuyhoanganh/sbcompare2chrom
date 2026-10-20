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
import stat
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


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def chromedriver_url(chromium_version: str, plat: str | None = None) -> tuple[str, str]:
    """(version, download url) of the chromedriver closest to ``chromium_version``:
    same build (x.y.BUILD) if Chrome for Testing has it, else the latest of the milestone."""
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
    with urllib.request.urlopen(url, timeout=300) as r:
        data = r.read()
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        member = next(n for n in z.namelist() if n.endswith("/" + EXE_NAME) or n == EXE_NAME)
        out = target_dir / EXE_NAME
        out.write_bytes(z.read(member))
    out.chmod(out.stat().st_mode | stat.S_IEXEC)
    (target_dir / "VERSION").write_text(version)
    return out


def resolve_chromedriver(configured: str, chromium_version: str | None, drivers_dir: Path = ROOT / "drivers") -> str:
    if configured:
        if not Path(configured).exists():
            raise FileNotFoundError(f"Configured chromedriver not found: {configured}")
        return configured
    if not chromium_version:
        raise RuntimeError("Cannot resolve chromedriver: no chromium version and no configured driver")
    local = drivers_dir / str(major(chromium_version)) / EXE_NAME
    if local.exists():
        return str(local)
    return str(download_chromedriver(chromium_version, local.parent))
