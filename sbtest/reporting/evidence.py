"""Evidence written when a test fails, and optional screenshots after every step."""
from __future__ import annotations

import base64
import os
import threading
from pathlib import Path

from sbtest.utils import log, slug

#: seconds allowed for the WebDriver part of the failure evidence
WEB_EVIDENCE_BUDGET = 30


def screen_grab(path: Path) -> Path:
    """Whole Windows screen - shows native dialogs/bubbles a WebDriver screenshot cannot see."""
    from PIL import ImageGrab

    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(all_screens=True).save(path)
    return path


def can_grab_screen(cfg) -> bool:
    return os.name == "nt" and not cfg.get("browser.headless")


def step_screenshot(session, run_dir: Path, nodeid: str, rec: dict, n: int) -> None:
    """``--screenshot-steps``: picture of the tab (and the screen on Windows) after a step."""
    if session is None or session.driver is None or session.web.has_alert():
        return
    out = run_dir / "steps" / slug(nodeid, 150)
    name = f"{n:02d}_{rec['status']}_{slug(rec['title'], 50)}"
    rec["screenshot"] = str(session.web.screenshot(out / f"{name}.png"))
    if can_grab_screen(session.cfg):
        rec["screen"] = str(screen_grab(out / f"{name}_screen.png"))


def result_screenshot(session, cfg, run_dir: Path, nodeid: str) -> str:
    """Picture of how a test ENDED (pass or fail), for the per-build report: the whole screen
    on Windows (native bubbles included), else the tab. Returns the path or ""."""
    out = run_dir / "results" / f"{slug(nodeid, 150)}.png"
    try:
        if can_grab_screen(cfg):
            return str(screen_grab(out))
        if session is not None and session.driver is not None and not session.web.has_alert():
            return str(session.web.screenshot(out))
    except Exception as e:  # noqa: BLE001 - a missing picture must not fail the test
        log.warning("result screenshot failed: %s", e)
    return ""


def collect_failure(session, cfg, run_dir: Path, res: dict) -> tuple[Path, list[str]]:
    """Write everything that helps explain a failure; returns (folder, saved file names)."""
    out = run_dir / "failures" / slug(res["nodeid"], 150)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    def _try(name, fn):
        try:
            fn()
            saved.append(name)
        except Exception as e:  # noqa: BLE001 - evidence is best effort
            log.warning("evidence %s failed: %s", name, e)

    alive = session is not None and session.driver is not None
    # OS-level evidence first: it never depends on the page (a print preview or another
    # modal browser UI can block every WebDriver command)
    if can_grab_screen(cfg) and cfg.get("report.screenshot_on_failure", True):
        _try("screen.png", lambda: screen_grab(out / "screen.png"))
    if alive and session.native is not None and cfg.get("report.uia_on_failure", True):
        _try("uia.txt", lambda: session.native.dump(out / "uia.txt"))

    def _web_evidence():
        if session.web.has_alert():
            _try("alert.txt", lambda: (out / "alert.txt").write_text(session.web.alert_text(timeout=1), encoding="utf-8"))
            return
        web = session.web
        if cfg.get("report.highlight_on_failure", True):
            web.highlight()
        if cfg.get("report.screenshot_on_failure", True):
            _try("page.png", lambda: web.screenshot(out / "page.png"))
        if cfg.get("report.dom_on_failure", True):
            from sbtest.tools.dom import dump_dom

            _try("dom.txt", lambda: (out / "dom.txt").write_text(
                f"# URL: {web.url}\n# TITLE: {web.title}\n# TABS: {len(web.tabs)}\n" + dump_dom(web), encoding="utf-8"))
            _try("page.html", lambda: (out / "page.html").write_text(session.driver.page_source, encoding="utf-8"))

    if alive:
        worker = threading.Thread(target=_web_evidence, daemon=True)
        worker.start()
        worker.join(WEB_EVIDENCE_BUDGET)
        if worker.is_alive():
            alive = False  # the page does not answer; do not touch the driver again here
            log.warning("web evidence skipped: page unresponsive after %ss (modal browser UI?)", WEB_EVIDENCE_BUDGET)
            (out / "page_unresponsive.txt").write_text(
                "WebDriver did not answer while collecting evidence: a modal browser UI (print preview, "
                "a native dialog) is probably blocking the page. See screen.png / uia.txt.\n", encoding="utf-8")
            saved.append("page_unresponsive.txt")

    target = session.web.last_target if alive else None
    if target and target[1] is not None and target[0].startswith("<selenium"):
        try:  # an element was passed instead of a locator: describe it by its markup
            outer = session.web.js("return arguments[0].outerHTML", target[1]) or ""
            target = (" ".join(outer.split())[:160], target[1])
        except Exception:  # noqa: BLE001 - stale element
            target = ("<element passed directly, now stale>", target[1])
    lines = [
        f"test: {res['nodeid']}",
        f"cases: {', '.join(res['cases']) or '-'}",
        f"failed step: {res['failed_step'] or '-'}",
        f"expected: {res['expected'] or '-'}",
        f"error: {res['message'] or '-'}",
        f"last element: {target[0] if target else '-'}" + ("  (NOT FOUND)" if target and target[1] is None else ""),
    ]
    if alive:
        try:
            lines.append(f"url: {session.web.url}")
        except Exception:  # noqa: BLE001 - browser gone
            pass
    (out / "failure.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    saved.insert(0, "failure.txt")
    return out, saved


def attach_to_html_report(rep, paths: list[Path]) -> None:
    """Embed screenshots in the self-contained pytest-html report (if the plugin is installed)."""
    try:
        from pytest_html import extras
    except ImportError:
        return
    extra = getattr(rep, "extras", [])
    for p in paths:
        if p.exists():
            extra.append(extras.png(base64.b64encode(p.read_bytes()).decode("ascii"), name=p.name))
    rep.extras = extra
