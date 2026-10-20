"""Download Chrome for Testing (+ the matching chromedriver) for the `chrome` reference target.

    python -m sbtest.tools.get_chrome                    # same Chromium major as the Samsung build
    python -m sbtest.tools.get_chrome --version 141      # a milestone or full version
    python -m sbtest.tools.get_chrome --version stable

Installs into browsers/chrome/ (config/targets/chrome.yaml points there) and
drivers/<major>/. Chrome for Testing is used rather than branded Google Chrome because it
accepts --load-extension (needed by the add-on tests) and has no auto-update.
Proxy: HTTPS_PROXY env var or network.download_proxy.
"""
from __future__ import annotations

import argparse
import json
import shutil

from sbtest.browser import driver_resolver as dr
from sbtest.browser.version import detect_chromium_version
from sbtest.config import ROOT, load_config


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--version", help="milestone (141), full version, or 'stable'. Default: the Samsung build's")
    args = p.parse_args(argv)
    cfg = load_config()
    dr._PROXY = cfg.get("network.download_proxy") or ""

    version = args.version
    if not version:
        sam = load_config({"target": "samsung"})
        if sam.get("browser.chromium_version"):
            version = sam.get("browser.chromium_version")
        elif sam.get("browser.exe") and sam.path("browser.exe").exists():
            version = detect_chromium_version(sam.path("browser.exe"), cfg.path("paths.artifacts") / ".cache")
        else:
            version = "stable"
    if version == "stable":
        stable = dr._get_json(f"{dr.CFT}/last-known-good-versions.json")["channels"]["Stable"]["version"]
        version = stable
    if version.isdigit():
        version = f"{version}.0.0.0"  # milestone -> latest of the milestone

    full, chrome_url = dr.chromedriver_url(version, artifact="chrome")
    target = ROOT / "browsers" / "chrome"
    if target.exists():
        shutil.rmtree(target)
    print(f"Chrome for Testing {full}: {chrome_url}")
    dr.download_zip(chrome_url, target)
    (target / "VERSION").write_text(full)
    driver = dr.download_chromedriver(full, ROOT / "drivers" / str(dr.major(full)))
    exe = target / ("chrome.exe" if dr.EXE_NAME.endswith(".exe") else "chrome")
    print(json.dumps({"chrome": str(exe), "chromedriver": str(driver), "version": full}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
