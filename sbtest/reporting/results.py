"""results.json - the machine-readable outcome of a run (input of the Confluence export)."""
from __future__ import annotations

import datetime as dt
import json
import platform
from pathlib import Path


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Results:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.meta: dict = {"started": now()}
        self.tests: dict[str, dict] = {}

    def record(self, nodeid: str, name: str, feature: str | None, cases: list[str], native: bool) -> dict:
        if nodeid not in self.tests:
            self.tests[nodeid] = {
                "nodeid": nodeid, "name": name, "feature": feature, "cases": cases, "native": native,
                "outcome": "passed", "duration": 0.0, "message": "", "failed_step": "", "expected": "",
                "steps": [], "evidence_dir": "", "evidence": [],
            }
        return self.tests[nodeid]

    def note_browser(self, session) -> None:
        """Browser/driver versions, taken once from the first session of the run."""
        if "browser_version" in self.meta:
            return
        try:
            caps = session.driver.capabilities
            self.meta["browser_version"] = caps.get("browserVersion", "")
            self.meta["chromedriver"] = (caps.get("chrome") or {}).get("chromedriverVersion", "")
            self.meta["user_agent"] = session.web.js("return navigator.userAgent")
        except Exception:  # noqa: BLE001 - informative only
            pass

    def write(self, cfg, exit_status: int) -> Path | None:
        if not self.tests:
            return None
        self.meta.update({"finished": now(), "exit_status": int(exit_status), "target": cfg.target,
                          "exe": cfg.get("browser.exe"), "machine": platform.node(), "os": platform.platform(),
                          "run_dir": str(self.run_dir)})
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / "results.json"
        path.write_text(json.dumps({"meta": self.meta, "tests": list(self.tests.values())}, indent=2, default=str),
                        encoding="utf-8")
        return path
