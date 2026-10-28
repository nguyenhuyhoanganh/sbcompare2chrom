"""pytest integration: options, markers, fixtures, results and failure evidence.

Fixtures (ask only for what the test needs):
    cfg            merged Config
    site           LocalSite - local deterministic web content
    session        BrowserSession for this test (fresh profile unless a shared scope is configured)
    web            session.web     - everything inside web content
    native         session.native  - browser UI / OS dialogs (test is skipped where unavailable)
    pages          page objects: pages.bookmarks, pages.extensions ...
    data           data("bookmarks") -> resources/data/bookmarks.yaml with {site} filled in
    downloads_dir  folder this browser profile downloads into

Markers:
    @pytest.mark.case("BM-001")   case ids from cases/ (filter: --case)
    @pytest.mark.native           drives native UI (Windows, not headless)
    @pytest.mark.browser(bookmarks=..., prefs={...}, args=[...], extensions=["sample_addon"], profile="name")
                                  preconditions applied BEFORE the browser starts
    @pytest.mark.sanity / slow
    Feature markers come from the folder: tests/features/<feature>/ -> <feature>.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from sbtest import steps
from sbtest.browser.session import BrowserSession
from sbtest.config import ROOT, load_config
from sbtest.data.loader import format_data, load_data
from sbtest.pages import Pages
from sbtest.reporting import evidence
from sbtest.reporting.cleanup import clear_dir
from sbtest.reporting.results import Results
from sbtest.server import LocalSite
from sbtest.utils import log

FEATURES = ("addons", "bookmarks", "downloads", "history", "general")
SKIP_NATIVE = "native UI not available (needs Windows, pywinauto, non-headless)"


# ------------------------------------------------------------------ options / markers
def pytest_addoption(parser):
    g = parser.getgroup("sbtest")
    g.addoption("--exe", help="SamsungInternet.exe (overrides browser.exe of the config)")
    g.addoption("--driver", help="chromedriver path")
    g.addoption("--mode", choices=["launch", "attach"], help="how chromedriver connects to the browser")
    g.addoption("--headless", action="store_true", default=None, help="headless (native tests are skipped)")
    g.addoption("--browser-scope", choices=["function", "module", "session"],
                help="reuse one browser per module/session for tests without @browser marker")
    g.addoption("--feature", help="comma list: addons,bookmarks,downloads,history,general")
    g.addoption("--case", help="comma list of test case ids, e.g. BM-001,DL-004")
    g.addoption("--keep-profile", action="store_true", default=None, help="keep profile folders for debugging")
    g.addoption("--run-dir", help="output folder of this run (default paths.results = artifacts/test-results, "
                                  "emptied when the run starts)")
    g.addoption("--screenshot-steps", action="store_true", default=False, help="screenshot after every step()")
    g.addoption("--sb-live", action="store_true", default=False,
                help="readable one-line-per-test output (run.py uses it with -p no:terminal)")


def pytest_configure(config):
    for f in FEATURES:
        config.addinivalue_line("markers", f"{f}: feature {f} (auto from tests/features/{f}/)")
    for line in ("case(*ids): test case ids from cases/", "native: drives native Windows UI (pywinauto)",
                 "browser(**opts): per-test browser preconditions", "slow: long running",
                 "sanity: part of the quick sanity pass"):
        config.addinivalue_line("markers", line)
    cfg = load_config({
        "browser.exe": config.getoption("--exe"),
        "browser.chromedriver": config.getoption("--driver"),
        "browser.mode": config.getoption("--mode"),
        "browser.headless": config.getoption("--headless"),
        "browser.scope": config.getoption("--browser-scope"),
        "browser.keep_profile": config.getoption("--keep-profile"),
        "report.screenshot_steps": True if config.getoption("--screenshot-steps") else None,
    })
    run_dir = config.getoption("--run-dir")
    run_dir = Path(run_dir) if run_dir else cfg.path("paths.results")
    config._sb_cfg = cfg
    config._sb_run_dir = run_dir
    config._sb_results = Results(run_dir)
    config._sb_write_results = True
    selection = [f"{opt}={config.getoption(opt)}" for opt in ("--feature", "--case") if config.getoption(opt)]
    if config.getoption("-m"):
        selection.append(f"-m {config.getoption('-m')}")
    config._sb_results.meta["selection"] = " ".join(selection) or "all"
    if config.getoption("--sb-live"):
        from sbtest.reporting.live import LiveReport

        config.pluginmanager.register(LiveReport(config), "sbtest-live")


def feature_of(item) -> str | None:
    try:
        parts = Path(str(item.fspath)).resolve().relative_to(ROOT / "tests").parts
    except ValueError:
        return None
    if parts[0] == "features" and len(parts) > 2:
        return parts[1]
    return None


def case_ids(item) -> list[str]:
    return [str(i) for m in item.iter_markers("case") for i in m.args]


def pytest_collection_modifyitems(config, items):
    cfg = config._sb_cfg
    features = {f.strip() for f in (config.getoption("--feature") or "").split(",") if f.strip()}
    cases = {c.strip().upper() for c in (config.getoption("--case") or "").split(",") if c.strip()}
    selected, deselected = [], []
    for item in items:
        feat = feature_of(item)
        if feat:
            item.add_marker(getattr(pytest.mark, feat))
        if item.get_closest_marker("native") and not cfg.native_enabled:
            item.add_marker(pytest.mark.skip(reason=SKIP_NATIVE))
        keep = (not features or feat in features) and (not cases or cases & {c.upper() for c in case_ids(item)})
        (selected if keep else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


BROWSER_FIXTURES = {"web", "native", "pages", "session", "site", "downloads_dir"}


def pytest_collection_finish(session):
    """Decide where this run writes. A run of product tests (tests/features) owns the results
    folder: it is emptied first and gets results.json + the report. Other runs never touch
    it: framework tests write nothing, scratch browser tests (tests/_scratch) write to
    artifacts/explore/scratch-run/. A --run-dir is used as given."""
    config = session.config
    if config.option.collectonly or hasattr(config, "workerinput") or config.getoption("--run-dir"):
        return
    cfg = config._sb_cfg
    artifacts = cfg.path("paths.artifacts")
    if any(feature_of(i) for i in session.items):
        for p in clear_dir(config._sb_run_dir, artifacts):
            log.warning("left from the previous run (in use, delete it by hand): %s", p)
        for old in ("runs", "logs", "profiles"):   # earlier layout: runs/<timestamp>/, shared logs/profiles
            shutil.rmtree(artifacts / old, ignore_errors=True)
        from sbtest.browser.profile import SHORT_ROOT, profiles_root

        if profiles_root(config._sb_run_dir / "profiles") == SHORT_ROOT:   # repo in a deep folder
            log.info("browser profiles in %s (the repo path is too long for them)", SHORT_ROOT)
            shutil.rmtree(SHORT_ROOT, ignore_errors=True)                  # leftovers of the last run
        return
    uses_browser = any(BROWSER_FIXTURES & set(getattr(i, "fixturenames", ())) for i in session.items)
    config._sb_write_results = uses_browser
    if uses_browser:
        scratch = artifacts / "explore" / "scratch-run"
        clear_dir(scratch, artifacts)
        config._sb_run_dir = scratch
        config._sb_results.run_dir = scratch


def pytest_report_header(config):
    cfg = config._sb_cfg
    return [f"sbtest: exe={cfg.get('browser.exe') or '<not set>'} mode={cfg.get('browser.mode')} "
            f"headless={cfg.get('browser.headless')} native={cfg.native_enabled} scope={cfg.get('browser.scope')}",
            f"sbtest: results={config._sb_run_dir}"]


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
    s = LocalSite(cfg.path("paths.site"), cfg.get("server.host"), int(cfg.get("server.port") or 0)).start()
    yield s
    s.stop()


@pytest.fixture
def data(site):
    """``data("bookmarks")`` -> dict from resources/data/bookmarks.yaml, ``{site}`` resolved."""
    return lambda name: load_data(name, site)


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
    exts = [Path(e) if Path(e).is_absolute() else cfg.path("paths.extensions") / e
            for e in opts.get("extensions", [])]
    session = BrowserSession(cfg, name=request.node.name, extra_args=opts.get("args"), extensions=exts,
                             prefs=opts.get("prefs"), out_dir=request.config._sb_run_dir)
    if opts.get("profile"):
        session.profile.copy_from(cfg.path("paths.profiles") / opts["profile"])
    bm = opts.get("bookmarks")
    if bm:
        if isinstance(bm, str):  # "key" in resources/data/bookmarks.yaml, or "file:key"
            name, _, key = bm.rpartition(":")
            bm = load_data(name or "bookmarks", site)[key]
        session.profile.bookmarks(format_data(bm, {"site": site.base}))
    session.start()
    if session.native is not None:
        # first-run bubbles (Samsung "has been updated") would cover the page and toolbar in
        # every test and in the report screenshots: close them once, right after start
        session.native.dismiss_startup_bubbles()
    request.config._sb_results.note_browser(session)
    return session


def _reset_shared(s: BrowserSession) -> None:
    """Leave a shared browser neutral: one tab on about:blank, no dialogs."""
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


@pytest.fixture
def web(session):
    return session.web


@pytest.fixture
def native(session):
    if session.native is None:
        pytest.skip(SKIP_NATIVE)
    return session.native


@pytest.fixture
def pages(web):
    return Pages(web)


@pytest.fixture
def downloads_dir(session) -> Path:
    return session.downloads_dir


@pytest.fixture(autouse=True)
def _steps_tracking(request, cfg):
    steps.reset()
    if cfg.get("report.screenshot_steps"):
        steps.set_listener(lambda rec, n: evidence.step_screenshot(
            getattr(request.node, "_sb_session", None), request.config._sb_run_dir, request.node.nodeid, rec, n))
    yield
    steps.set_listener(None)


# ------------------------------------------------------------------ results + failure evidence
def _steps_section(hist: list[dict]) -> str:
    return "\n".join(f"[{s['status']:>7}] {s['title']}" + (f"  (expected: {s['expected']})" if s["expected"] else "")
                     + (f"\n          {s['error']}" if s.get("error") else "") for s in hist)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    rep = (yield).get_result()
    res = item.config._sb_results.record(item.nodeid, item.name, feature_of(item), case_ids(item),
                                         bool(item.get_closest_marker("native")))
    res["duration"] = round(res["duration"] + rep.duration, 2)
    if rep.when == "call" or (rep.when == "setup" and rep.failed):
        hist = steps.history()
        res["steps"] = [{k: v for k, v in s.items() if k != "start"} for s in hist]
        if hist:
            rep.sections.append(("sbtest steps", _steps_section(hist)))
        failed = [s for s in hist if s["status"] == "failed"]
        if failed:
            res["failed_step"], res["expected"] = failed[-1]["title"], failed[-1]["expected"]
    if rep.when == "call" and rep.passed:  # also clears a failure from an earlier rerun
        res.update(outcome="passed", message="", failed_step="", expected="", evidence_dir="", evidence=[])
        if item.config._sb_cfg.get("report.result_screenshot", True):
            res["screenshot"] = evidence.result_screenshot(getattr(item, "_sb_session", None), item.config._sb_cfg,
                                                           item.config._sb_run_dir, item.nodeid)
    if rep.skipped:
        res["outcome"] = "skipped"
        res["message"] = str(rep.longrepr[-1]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr or "")
    elif rep.failed:
        res["outcome"] = "failed" if rep.when == "call" else "error"
        crash = getattr(rep.longrepr, "reprcrash", None)
        lines = (rep.longreprtext or "").strip().splitlines()
        message = crash.message if crash else (lines[-1] if lines else "")
        # chromedriver appends a native stacktrace ("Stacktrace:\n#0 0x...") - keep the readable part
        # the "[sbtest] failed at step" note repeats failed_step / expected, stored on their own
        message = message.split("\n[sbtest] failed at step")[0]
        res["message"] = message.split("\nStacktrace:")[0].split("; For documentation")[0].strip()[:600]
        if rep.when in ("setup", "call"):
            try:
                out, saved = evidence.collect_failure(getattr(item, "_sb_session", None), item.config._sb_cfg,
                                                      item.config._sb_run_dir, res)
                res["evidence_dir"], res["evidence"] = str(out), saved
                shot = next((out / n for n in ("screen.png", "page.png") if (out / n).exists()), None)
                res["screenshot"] = str(shot) if shot else ""
                rep.sections.append(("sbtest evidence", f"{out}\n" + ", ".join(saved)))
                evidence.attach_to_html_report(rep, [out / "page.png", out / "screen.png"])
            except Exception as e:  # noqa: BLE001 - never let evidence break the run
                rep.sections.append(("sbtest evidence", f"evidence collection failed: {type(e).__name__}: {e}"))


def pytest_sessionfinish(session, exitstatus):
    _shared.close_except(None)
    config = session.config
    if not config._sb_write_results:
        return
    path = config._sb_results.write(config._sb_cfg, int(exitstatus))
    if path and os.environ.get("SB_NO_EXPORT") != "1":
        try:
            from sbtest.reporting.report import generate

            log.info("sanity report: %s", generate(path.parent))
        except Exception as e:  # noqa: BLE001 - the run result matters more than the report
            log.warning("report generation failed: %s", e)
        try:
            from sbtest.reporting.confluence_export import export

            export(path.parent)
        except Exception as e:  # noqa: BLE001
            log.warning("confluence export failed: %s", e)
