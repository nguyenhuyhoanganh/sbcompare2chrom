"""pytest integration: options, markers, fixtures, failure evidence.

Fixtures (use only what you need in a test signature):
    cfg        merged Config
    site       LocalSite (local deterministic web content)
    session    BrowserSession for this test (fresh profile unless shared scope)
    web        session.web     - web content actions/reads/waits
    native     session.native  - native UI (test auto-skips if unavailable)
    pages      Pages(web)      - page objects: pages.bookmarks, pages.history ...
    data       data("bookmarks") -> test_data/bookmarks.yaml with {site} filled in
    downloads_dir              - folder the browser downloads into for this session

Markers:
    @pytest.mark.case("BM-001", "BM-002")  ids from testcases/*.md (filter with --case)
    @pytest.mark.native                    needs native UI (Windows, not headless)
    @pytest.mark.browser(bookmarks="seed_basic" | {...}, prefs={...}, args=[...],
                         extensions=["sample_addon"], profile="template_name")
                                           preconditions applied BEFORE the browser starts
    feature markers (bookmarks, history, downloads, settings, addons, general) are added
    automatically from the folder name under tests/.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

import pytest

from sbtest import steps
from sbtest.browser.session import BrowserSession
from sbtest.config import ROOT, load_config
from sbtest.data.loader import format_data, load_data
from sbtest.pages import Pages
from sbtest.server import LocalSite
from sbtest.utils import log, slug

FEATURES = ("bookmarks", "history", "downloads", "settings", "addons", "general")
RUN_ID = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


# ------------------------------------------------------------------ options/markers
def pytest_addoption(parser):
    g = parser.getgroup("sbtest")
    g.addoption("--exe", help="path to SamsungInternet.exe (or any Chromium build)")
    g.addoption("--driver", help="path to chromedriver")
    g.addoption("--mode", choices=["launch", "attach"], help="how chromedriver connects")
    g.addoption("--headless", action="store_true", default=None, help="headless (native tests skip)")
    g.addoption("--browser-scope", choices=["function", "module", "session"],
                help="reuse one browser per module/session for tests without @browser marker")
    g.addoption("--feature", help="comma list of features to run, e.g. bookmarks,history")
    g.addoption("--case", help="comma list of test case ids, e.g. BM-001,HIS-003")
    g.addoption("--keep-profile", action="store_true", default=None, help="keep profile dirs for debugging")
    g.addoption("--run-dir", help="artifacts folder of this run (default artifacts/runs/<timestamp>)")


def pytest_configure(config):
    for f in FEATURES:
        config.addinivalue_line("markers", f"{f}: feature {f} (auto from tests/{f}/)")
    config.addinivalue_line("markers", "case(*ids): test case ids from testcases/ docs")
    config.addinivalue_line("markers", "native: needs native Windows UI automation (pywinauto)")
    config.addinivalue_line("markers", "browser(**opts): per-test browser preconditions")
    config.addinivalue_line("markers", "slow: long running")
    config.addinivalue_line("markers", "sanity: part of the quick sanity pass")
    config._sb_cfg = load_config({
        "browser.exe": config.getoption("--exe"),
        "browser.chromedriver": config.getoption("--driver"),
        "browser.mode": config.getoption("--mode"),
        "browser.headless": config.getoption("--headless"),
        "browser.scope": config.getoption("--browser-scope"),
        "browser.keep_profile": config.getoption("--keep-profile"),
    })
    run_dir = config.getoption("--run-dir")
    config._sb_run_dir = Path(run_dir) if run_dir else config._sb_cfg.path("paths.artifacts") / "runs" / RUN_ID


def _feature_of(item) -> str | None:
    try:
        rel = Path(str(item.fspath)).resolve().relative_to(ROOT / "tests")
    except ValueError:
        return None
    return rel.parts[0] if len(rel.parts) > 1 else None


def _case_ids(item) -> list[str]:
    return [str(i) for m in item.iter_markers("case") for i in m.args]


def pytest_collection_modifyitems(config, items):
    cfg = config._sb_cfg
    features = {f.strip() for f in (config.getoption("--feature") or "").split(",") if f.strip()}
    cases = {c.strip().upper() for c in (config.getoption("--case") or "").split(",") if c.strip()}
    selected, deselected = [], []
    for item in items:
        feat = _feature_of(item)
        if feat:
            item.add_marker(getattr(pytest.mark, feat))
        if item.get_closest_marker("native") and not cfg.native_enabled:
            item.add_marker(pytest.mark.skip(reason="native UI not available (needs Windows, pywinauto, non-headless)"))
        keep = (not features or feat in features) and (not cases or cases & {c.upper() for c in _case_ids(item)})
        (selected if keep else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="session")
def cfg(request):
    return request.config._sb_cfg


@pytest.fixture(scope="session")
def run_dir(request) -> Path:
    d = request.config._sb_run_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def site(cfg):
    s = LocalSite(cfg.path("paths.test_site"), cfg.get("server.host"), int(cfg.get("server.port") or 0)).start()
    yield s
    s.stop()


@pytest.fixture
def data(site):
    """``data("bookmarks")`` -> dict from test_data/bookmarks.yaml, ``{site}`` resolved."""
    return lambda feature: load_data(feature, site)


class _Shared:
    """One reusable session per scope key when browser.scope is module/session."""

    def __init__(self):
        self.sessions: dict[str, BrowserSession] = {}

    def get(self, key: str, factory) -> BrowserSession:
        s = self.sessions.get(key)
        if s is None or s.driver is None:
            s = self.sessions[key] = factory()
        return s

    def close_except(self, keep: str | None = None) -> None:
        for k in list(self.sessions):
            if k != keep:
                self.sessions.pop(k).stop()


_shared = _Shared()


def _build_session(cfg, site, request) -> BrowserSession:
    m = request.node.get_closest_marker("browser")
    opts = dict(m.kwargs) if m else {}
    exts = []
    for e in opts.get("extensions", []):
        p = Path(e)
        exts.append(p if p.is_absolute() else cfg.path("paths.test_data") / "extensions" / e)
    session = BrowserSession(cfg, name=request.node.name, extra_args=opts.get("args"), extensions=exts,
                             prefs=opts.get("prefs"))
    if opts.get("profile"):
        session.profile.copy_from(cfg.path("paths.test_data") / "profiles" / opts["profile"])
    bm = opts.get("bookmarks")
    if bm:
        if isinstance(bm, str):  # key in test_data/<feature>.yaml (or "feature:key")
            feature, _, key = bm.rpartition(":")
            bm = load_data(feature or _feature_of(request.node) or "bookmarks", site)[key]
        session.profile.bookmarks(format_data(bm, {"site": site.base}))
    return session.start()


@pytest.fixture
def session(cfg, site, request):
    scope = cfg.get("browser.scope", "function")
    if scope == "function" or request.node.get_closest_marker("browser"):
        s = _build_session(cfg, site, request)
        request.node._sb_session = s
        yield s
        s.stop()
        return
    key = "session" if scope == "session" else str(request.node.fspath)
    _shared.close_except(key)
    s = _shared.get(key, lambda: _build_session(cfg, site, request))
    request.node._sb_session = s
    yield s
    _reset_shared(s)


def _reset_shared(s: BrowserSession) -> None:
    """Leave a shared browser in a neutral state: one tab on about:blank, no dialogs."""
    try:
        if s.web.has_alert():
            s.web.dismiss_alert()
        tabs = s.web.tabs
        for h in tabs[1:]:
            s.driver.switch_to.window(h)
            s.driver.close()
        s.driver.switch_to.window(tabs[0])
        s.web.open("about:blank")
        if s.native:
            s.native.close_stray_dialogs()
    except Exception as e:  # noqa: BLE001 - broken session: drop it
        log.warning("shared session reset failed (%s); restarting", e)
        s.stop()


def pytest_sessionfinish(session, exitstatus):
    _shared.close_except(None)


@pytest.fixture
def web(session):
    return session.web


@pytest.fixture
def native(session):
    if session.native is None:
        pytest.skip("native UI not available (needs Windows, pywinauto, non-headless)")
    return session.native


@pytest.fixture
def pages(web):
    return Pages(web)


@pytest.fixture
def downloads_dir(session) -> Path:
    return session.downloads_dir


@pytest.fixture(autouse=True)
def _steps_reset():
    steps.reset()
    yield


# ------------------------------------------------------------------ failure evidence
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" or (rep.when == "setup" and rep.failed):
        hist = steps.history()
        if hist:
            rep.sections.append(("sbtest steps", "\n".join(
                f"[{s['status']:>7}] {s['title']}" + (f"  (expected: {s['expected']})" if s["expected"] else "")
                + (f"\n          {s['error']}" if s.get("error") else "") for s in hist)))
    if rep.failed and rep.when in ("setup", "call"):
        try:
            _collect_evidence(item, rep)
        except Exception as e:  # noqa: BLE001 - never let evidence break the run
            rep.sections.append(("sbtest evidence", f"evidence collection failed: {type(e).__name__}: {e}"))


def _collect_evidence(item, rep) -> None:
    s: BrowserSession | None = getattr(item, "_sb_session", None)
    if s is None or s.driver is None:
        return
    cfg = s.cfg
    out = item.config._sb_run_dir / "failures" / slug(item.nodeid, 150)
    out.mkdir(parents=True, exist_ok=True)
    saved = []

    def _try(name, fn):
        try:
            fn()
            saved.append(name)
        except Exception as e:  # noqa: BLE001 - evidence is best effort
            log.warning("evidence %s failed: %s", name, e)

    if s.web.has_alert():
        _try("alert.txt", lambda: (out / "alert.txt").write_text(s.web.alert_text(timeout=1)))
    else:
        if cfg.get("report.screenshot_on_failure", True):
            _try("page.png", lambda: s.web.screenshot(out / "page.png"))
        if cfg.get("report.dom_on_failure", True):
            from sbtest.tools.dom import dump_dom

            _try("dom.txt", lambda: (out / "dom.txt").write_text(
                f"# URL: {s.web.url}\n# TITLE: {s.web.title}\n# TABS: {len(s.web.tabs)}\n" + dump_dom(s.web),
                encoding="utf-8"))
            _try("page.html", lambda: (out / "page.html").write_text(s.driver.page_source, encoding="utf-8"))
    if s.native is not None and cfg.get("report.uia_on_failure", True):
        _try("screen.png", lambda: s.native.screenshot(out / "screen.png"))
        _try("uia.txt", lambda: s.native.dump(out / "uia.txt"))
    rep.sections.append(("sbtest evidence", f"{out}\n" + ", ".join(saved)))
    try:
        from pytest_html import extras  # optional

        extra = getattr(rep, "extras", [])
        if (out / "page.png").exists():
            extra.append(extras.image(str((out / "page.png").relative_to(item.config._sb_run_dir))))
        if (out / "screen.png").exists():
            extra.append(extras.image(str((out / "screen.png").relative_to(item.config._sb_run_dir))))
        rep.extras = extra
    except ImportError:
        pass


def pytest_report_header(config):
    cfg = config._sb_cfg
    return [f"sbtest: exe={cfg.get('browser.exe') or '<not set>'} mode={cfg.get('browser.mode')} "
            f"headless={cfg.get('browser.headless')} native={cfg.native_enabled} scope={cfg.get('browser.scope')}",
            f"sbtest: artifacts={config._sb_run_dir}  (os={os.name})"]
