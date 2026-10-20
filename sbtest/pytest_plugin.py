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
    g.addoption("--screenshot-steps", action="store_true", default=False, help="screenshot after every step()")


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
    if config.getoption("--screenshot-steps"):
        config._sb_cfg.data.setdefault("report", {})["screenshot_steps"] = True
    config._sb_results = {}
    config._sb_meta = {"started": _dt.datetime.now().isoformat(timespec="seconds")}
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
    session.start()
    meta = request.config._sb_meta
    if "browser_version" not in meta:
        try:
            meta["browser_version"] = session.driver.capabilities.get("browserVersion", "")
            meta["user_agent"] = session.web.js("return navigator.userAgent")
            meta["chromedriver"] = (session.driver.capabilities.get("chrome") or {}).get("chromedriverVersion", "")
        except Exception:  # noqa: BLE001
            pass
    return session


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
def _steps_reset(request, cfg):
    steps.reset()
    if cfg.get("report.screenshot_steps"):
        steps.set_listener(lambda rec, n: _step_screenshot(request.node, rec, n))
    yield
    steps.set_listener(None)


def _step_screenshot(item, rec: dict, n: int) -> None:
    """``--screenshot-steps``: picture of the tab (and the screen on Windows) after each step."""
    s: BrowserSession | None = getattr(item, "_sb_session", None)
    if s is None or s.driver is None or s.web.has_alert():
        return
    out = item.config._sb_run_dir / "steps" / slug(item.nodeid, 150)
    name = f"{n:02d}_{rec['status']}_{slug(rec['title'], 50)}"
    rec["screenshot"] = str(s.web.screenshot(out / f"{name}.png"))
    if os.name == "nt" and not s.cfg.get("browser.headless"):
        rec["screen"] = str(_screen_grab(out / f"{name}_screen.png"))


def _screen_grab(path: Path) -> Path:
    from PIL import ImageGrab

    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(all_screens=True).save(path)
    return path


# ------------------------------------------------------------------ results + failure evidence
def _result(item) -> dict:
    results = item.config._sb_results
    if item.nodeid not in results:
        results[item.nodeid] = {
            "nodeid": item.nodeid, "name": item.name, "feature": _feature_of(item), "cases": _case_ids(item),
            "native": bool(item.get_closest_marker("native")), "outcome": "passed", "duration": 0.0,
            "message": "", "failed_step": "", "expected": "", "steps": [], "evidence_dir": "", "evidence": [],
        }
    return results[item.nodeid]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    res = _result(item)
    res["duration"] = round(res["duration"] + rep.duration, 2)
    if rep.when == "call" or (rep.when == "setup" and rep.failed):
        hist = steps.history()
        res["steps"] = [{k: v for k, v in st.items() if k != "start"} for st in hist]
        if hist:
            rep.sections.append(("sbtest steps", "\n".join(
                f"[{st['status']:>7}] {st['title']}" + (f"  (expected: {st['expected']})" if st["expected"] else "")
                + (f"\n          {st['error']}" if st.get("error") else "") for st in hist)))
        failed = [st for st in hist if st["status"] == "failed"]
        if failed:
            res["failed_step"], res["expected"] = failed[-1]["title"], failed[-1]["expected"]
    if rep.when == "call" and rep.passed:  # also resets a failure from an earlier rerun
        res.update(outcome="passed", message="", failed_step="", expected="", evidence_dir="", evidence=[])
    if rep.skipped:
        res["outcome"] = "skipped"
        res["message"] = str(rep.longrepr[-1]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr or "")
    elif rep.failed:
        res["outcome"] = "error" if rep.when != "call" else "failed"
        crash = getattr(rep.longrepr, "reprcrash", None)
        lines = (rep.longreprtext or "").strip().splitlines()
        res["message"] = (crash.message if crash else (lines[-1] if lines else ""))[:800]
        if rep.when in ("setup", "call"):
            try:
                _collect_evidence(item, rep, res)
            except Exception as e:  # noqa: BLE001 - never let evidence break the run
                rep.sections.append(("sbtest evidence", f"evidence collection failed: {type(e).__name__}: {e}"))


def _collect_evidence(item, rep, res: dict) -> None:
    s: BrowserSession | None = getattr(item, "_sb_session", None)
    out = item.config._sb_run_dir / "failures" / slug(item.nodeid, 150)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    def _try(name, fn):
        try:
            fn()
            saved.append(name)
        except Exception as e:  # noqa: BLE001 - evidence is best effort
            log.warning("evidence %s failed: %s", name, e)

    cfg = item.config._sb_cfg
    alive = s is not None and s.driver is not None
    if alive and s.web.has_alert():
        _try("alert.txt", lambda: (out / "alert.txt").write_text(s.web.alert_text(timeout=1), encoding="utf-8"))
    elif alive:
        if cfg.get("report.highlight_on_failure", True):
            s.web.highlight()
        if cfg.get("report.screenshot_on_failure", True):
            _try("page.png", lambda: s.web.screenshot(out / "page.png"))
        if cfg.get("report.dom_on_failure", True):
            from sbtest.tools.dom import dump_dom

            _try("dom.txt", lambda: (out / "dom.txt").write_text(
                f"# URL: {s.web.url}\n# TITLE: {s.web.title}\n# TABS: {len(s.web.tabs)}\n" + dump_dom(s.web),
                encoding="utf-8"))
            _try("page.html", lambda: (out / "page.html").write_text(s.driver.page_source, encoding="utf-8"))
    # whole screen: shows native dialogs/bubbles a WebDriver screenshot cannot see
    if os.name == "nt" and not cfg.get("browser.headless") and cfg.get("report.screenshot_on_failure", True):
        _try("screen.png", lambda: _screen_grab(out / "screen.png"))
    if alive and s.native is not None and cfg.get("report.uia_on_failure", True):
        _try("uia.txt", lambda: s.native.dump(out / "uia.txt"))

    target = s.web.last_target if alive else None
    summary = [
        f"test: {item.nodeid}",
        f"cases: {', '.join(res['cases']) or '-'}",
        f"failed step: {res['failed_step'] or '-'}",
        f"expected: {res['expected'] or '-'}",
        f"error: {res['message'] or '-'}",
        f"last element: {target[0] if target else '-'}" + ("" if not target or target[1] is not None else "  (NOT FOUND)"),
    ]
    if alive:
        try:
            summary.append(f"url: {s.web.url}")
        except Exception:  # noqa: BLE001
            pass
    (out / "failure.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    saved.insert(0, "failure.txt")
    res["evidence_dir"], res["evidence"] = str(out), saved
    rep.sections.append(("sbtest evidence", f"{out}\n" + ", ".join(saved)))
    _attach_html_images(rep, [out / "page.png", out / "screen.png"])


def _attach_html_images(rep, paths: list[Path]) -> None:
    """Embed screenshots into the self-contained pytest-html report."""
    try:
        from pytest_html import extras
    except ImportError:
        return
    import base64

    extra = getattr(rep, "extras", [])
    for p in paths:
        if p.exists():
            extra.append(extras.png(base64.b64encode(p.read_bytes()).decode("ascii"), name=p.name))
    rep.extras = extra


def pytest_sessionfinish(session, exitstatus):
    _shared.close_except(None)
    config = session.config
    if not getattr(config, "_sb_results", None):
        return
    import json
    import platform

    meta = dict(config._sb_meta)
    meta.update({"finished": _dt.datetime.now().isoformat(timespec="seconds"), "exit_status": int(exitstatus),
                 "machine": platform.node(), "os": platform.platform(),
                 "exe": config._sb_cfg.get("browser.exe"), "run_dir": str(config._sb_run_dir)})
    data = {"meta": meta, "tests": list(config._sb_results.values())}
    config._sb_run_dir.mkdir(parents=True, exist_ok=True)
    (config._sb_run_dir / "results.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def pytest_report_header(config):
    cfg = config._sb_cfg
    return [f"sbtest: exe={cfg.get('browser.exe') or '<not set>'} mode={cfg.get('browser.mode')} "
            f"headless={cfg.get('browser.headless')} native={cfg.native_enabled} scope={cfg.get('browser.scope')}",
            f"sbtest: artifacts={config._sb_run_dir}  (os={os.name})"]
