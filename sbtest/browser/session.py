"""BrowserSession: start/stop/restart the browser on an isolated profile.

    session = BrowserSession(cfg, name="test_x")
    session.profile.bookmarks({...})        # seed BEFORE start
    session.start()
    session.web.open("https://example.com")  # web layer (Selenium)
    session.native.hotkey("^d")             # native layer (pywinauto), Windows only
    session.restart()                       # same profile -> persistence checks
    session.stop()
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from sbtest.browser.driver_resolver import resolve_chromedriver
from sbtest.browser.profile import Profile
from sbtest.browser.version import detect_chromium_version, wait_devtools_port
from sbtest.config import Config
from sbtest.web.web import Web
from sbtest.utils import find_browser_pid, kill_tree, log, poll

_RESOLVED: dict[str, tuple[str, str]] = {}  # exe -> (chromium_version, chromedriver) per process


def _bypass_proxy_for_localhost() -> None:
    """HTTP(S)_PROXY env vars (company proxy) must not be used to reach the local
    chromedriver, DevTools or the local test site."""
    for var in ("NO_PROXY", "no_proxy"):
        current = [h.strip() for h in os.environ.get(var, "").split(",") if h.strip()]
        os.environ[var] = ",".join(current + [h for h in ("localhost", "127.0.0.1") if h not in current])


class BrowserSession:
    def __init__(self, cfg: Config, name: str = "", profile: Profile | None = None,
                 extra_args: list[str] | None = None, extensions: list[str | Path] | None = None,
                 prefs: dict | None = None) -> None:
        self.cfg = cfg
        self.name = name
        self.artifacts = cfg.path("paths.artifacts")
        self.profile = profile or Profile(self.artifacts / "profiles", name)
        self.extra_args = list(extra_args or [])
        self.extensions = [str(Path(e).resolve()) for e in (extensions or [])]
        self.extra_prefs = prefs or {}
        self.driver: webdriver.Chrome | None = None
        self.web: Web | None = None
        self._native = None
        self._attach_proc: subprocess.Popen | None = None
        self._prefs_seeded = False
        self.pid: int | None = None

    # -- resolution --------------------------------------------------------------
    @property
    def exe(self) -> str:
        if not self.cfg.get("browser.exe"):
            raise RuntimeError(f"Browser exe not set for target {self.cfg.target!r}: use --exe, SB_EXE or "
                               f"config/local.yaml targets.{self.cfg.target}.browser.exe")
        exe = self.cfg.path("browser.exe")  # relative paths are relative to the repo root
        if not exe.exists():
            hint = " (run: python -m sbtest.tools.get_chrome)" if self.cfg.target == "chrome" else ""
            raise FileNotFoundError(f"Browser exe not found: {exe}{hint}")
        return str(exe)

    def resolve(self) -> tuple[str, str]:
        exe = self.exe
        if exe not in _RESOLVED:
            version = self.cfg.get("browser.chromium_version") or ""
            driver = self.cfg.get("browser.chromedriver") or ""
            if not driver and not version:
                version = detect_chromium_version(exe, self.artifacts / ".cache", self._browser_args(probe=True))
            _RESOLVED[exe] = (version, resolve_chromedriver(driver, version,
                                                            proxy=self.cfg.get("network.download_proxy") or ""))
            log.info("Browser %s | chromium %s | chromedriver %s", exe, *_RESOLVED[exe])
        return _RESOLVED[exe]

    # -- options -----------------------------------------------------------------
    def _browser_args(self, probe: bool = False) -> list[str]:
        args = list(self.cfg.get("browser.args") or [])
        if self.cfg.get("browser.headless"):
            args.append("--headless=new")
        if os.name != "nt" and os.geteuid() == 0:
            args += ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]  # Linux CI containers only
        if probe:
            return args
        w, h = self.cfg.get("browser.window_size") or (1400, 900)
        args += [f"--window-size={w},{h}", f"--user-data-dir={self.profile.dir}"]
        proxy = self.cfg.get("network.browser_proxy")
        if proxy:
            args += [f"--proxy-server={proxy}", f"--proxy-bypass-list={self.cfg.get('network.proxy_bypass') or '<local>'}"]
        if self.extensions:
            joined = ",".join(self.extensions)
            # Chromium 137+ gates --load-extension behind this feature
            args += [f"--load-extension={joined}", f"--disable-extensions-except={joined}",
                     "--disable-features=DisableLoadExtensionCommandLineSwitch"]
        return args + self.extra_args

    def _seed_prefs(self) -> None:
        if self._prefs_seeded:  # restart(): keep what the test changed
            return
        self._prefs_seeded = True
        prefs = dict(self.cfg.get("browser.prefs") or {})
        prefs["download.default_directory"] = str(self.profile.downloads)
        prefs["savefile.default_directory"] = str(self.profile.downloads)
        prefs.update(self.extra_prefs)
        self.profile.prefs(prefs)

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> "BrowserSession":
        _, driver_path = self.resolve()
        self._seed_prefs()
        opts = webdriver.ChromeOptions()
        log_dir = self.artifacts / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        service = Service(driver_path, log_output=str(log_dir / f"chromedriver_{self.profile.dir.name}.log"))
        if self.cfg.get("browser.mode") == "attach":
            # restart(): the previous run's port file would point chromedriver at a dead port
            (self.profile.dir / "DevToolsActivePort").unlink(missing_ok=True)
            self._attach_proc = subprocess.Popen([self.exe, *self._browser_args(), "--remote-debugging-port=0",
                                                  "about:blank"])
            port = wait_devtools_port(self.profile.dir)
            opts.debugger_address = f"127.0.0.1:{port}"
        else:
            opts.binary_location = self.exe
            for a in self._browser_args():
                opts.add_argument(a)
            if self.cfg.get("browser.exclude_switches"):
                opts.add_experimental_option("excludeSwitches", list(self.cfg.get("browser.exclude_switches")))
        _bypass_proxy_for_localhost()
        self.driver = webdriver.Chrome(options=opts, service=service)
        self.driver.set_page_load_timeout(float(self.cfg.get("timeouts.page_load", 30)))
        self.pid = self._attach_proc.pid if self._attach_proc else find_browser_pid(str(self.profile.dir))
        self.web = Web(self.driver, self.cfg, native_factory=lambda: self.native)
        log.info("Started browser pid=%s profile=%s", self.pid, self.profile.dir)
        return self

    @property
    def native(self):
        """pywinauto wrapper of this browser's windows (None when native is disabled)."""
        if not self.cfg.native_enabled:
            return None
        if self._native is None:
            from sbtest.native.browser_ui import NativeBrowser

            pid = self.pid or poll(lambda: find_browser_pid(str(self.profile.dir)), 15, message="browser pid")
            self._native = NativeBrowser(pid, self.cfg)
        return self._native

    @property
    def downloads_dir(self) -> Path:
        return self.profile.downloads

    def stop(self, remove_profile: bool | None = None) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception as e:  # noqa: BLE001 - browser may already be gone
                log.warning("driver.quit failed: %s", e)
        for pid in filter(None, [self._attach_proc.pid if self._attach_proc else None,
                                 find_browser_pid(str(self.profile.dir))]):
            kill_tree(pid)
        self.driver = self.web = self._native = self._attach_proc = None
        self.pid = None
        if remove_profile if remove_profile is not None else not self.cfg.get("browser.keep_profile"):
            self.profile.remove()

    def restart(self) -> "BrowserSession":
        """Close and reopen on the same profile (checks that data/settings persist).

        Closes through the browser itself (CDP Browser.close) so it flushes prefs and
        bookmarks to disk like a user quitting; kills it only if that does not work.
        """
        if self.driver is not None:
            pid = find_browser_pid(str(self.profile.dir))
            try:
                self.driver.execute_cdp_cmd("Browser.close", {})
            except Exception as e:  # noqa: BLE001 - connection drops while closing
                log.debug("Browser.close: %s", e)
            if pid:
                try:
                    poll(lambda: find_browser_pid(str(self.profile.dir)) is None, 15, message="browser exit")
                except TimeoutError:
                    log.warning("browser did not exit gracefully, killing it")
        self.stop(remove_profile=False)
        return self.start()

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
