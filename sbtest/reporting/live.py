"""Readable live output of a test run - what run.py shows instead of pytest's own output.

One line per test, grouped by feature: result tag, case id, case title (the case docs), time,
progress. A failed test gets four more lines: the step that failed, what was expected, the
error in one line and the evidence folder - enough for a person or an agent to know what to
open next. ``run.py --raw`` gives pytest's own output back (tracebacks, captured logs).

    addons
      [PASS] ADD-112  Pinned add-on icon opens its popup                     6.1s   12/73
      [FAIL] BM-114   Remove a bookmark with the filled star                21.0s   13/73
             step:     1. Click the filled star
             expected: page no longer bookmarked
             error:    TimeoutError: Timed out after 10.0s: star no longer filled
             evidence: artifacts\\test-results\\failures\\...\\failure.txt (+ screen.png, page.png)
"""
from __future__ import annotations

from pathlib import Path

from sbtest.config import ROOT
from sbtest.tools import console

TAGS = {"passed": ("[PASS]", console.OK), "failed": ("[FAIL]", console.FAIL), "error": ("[ERR ]", console.FAIL),
        "skipped": ("[SKIP]", console.WARN), "rerun": ("[RERUN]", console.WARN)}


def _short(path: str | Path) -> str:
    p = Path(path)
    return str(p.relative_to(ROOT)) if p.is_absolute() and p.is_relative_to(ROOT) else str(p)


def _one_line(text: str, limit: int = 220) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= limit else line[:limit - 3] + "..."


class LiveReport:
    def __init__(self, config) -> None:
        self.config = config
        self.total = self.done = 0
        self.feature = None
        self.counts: dict[str, int] = {}
        try:
            from sbtest.reporting.cases import load_cases

            self.cases = load_cases()
        except Exception:  # noqa: BLE001 - titles are a nicety
            self.cases = {}

    # -- start -------------------------------------------------------------------
    def pytest_collection_finish(self, session) -> None:
        self.total = len(session.items)
        cfg = self.config._sb_cfg
        exe = cfg.get("browser.exe") or "(browser.exe not set)"
        from sbtest.reporting.results import exe_version

        version = exe_version(exe) if exe else ""
        console.title(f"sbtest - {self.total} test(s) on Samsung Browser {version}".rstrip())
        print(f"  exe:      {exe}")
        print(f"  results:  {_short(self.config._sb_run_dir)}")
        if not self.total:
            print(console.paint("  no test matches the selection (python run.py --list shows the cases)", console.WARN))
            return
        console.note("hands off the mouse and keyboard until the run ends")

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            lines = (report.longreprtext or "").strip().splitlines()
            console.check(console.FAIL, f"cannot load {report.nodeid}", _one_line(lines[-1] if lines else ""))

    # -- per test ----------------------------------------------------------------
    def pytest_runtest_logreport(self, report) -> None:
        if report.outcome == "rerun":
            self._line(report, "rerun")
            return
        if report.when == "setup" and report.skipped:
            self._line(report, "skipped")
        elif report.when == "setup" and report.failed:
            self._line(report, "error")
        elif report.when == "call":
            self._line(report, "passed" if report.passed else "skipped" if report.skipped else "failed")
        elif report.when == "teardown" and report.failed:
            self._line(report, "error", teardown=True)

    def _line(self, report, outcome: str, teardown: bool = False) -> None:
        res = self.config._sb_results.tests.get(report.nodeid, {})
        feature = res.get("feature") or "other"
        if feature != self.feature:
            self.feature = feature
            print("\n" + console.paint(feature, "bold"), flush=True)
        if outcome != "rerun" and not teardown:
            self.done += 1
            self.counts[outcome] = self.counts.get(outcome, 0) + 1
        ids = ", ".join(res.get("cases") or []) or "-"
        case = self.cases.get((res.get("cases") or [""])[0])
        title = case.title if case else report.nodeid.split("::")[-1].removeprefix("test_").replace("_", " ")
        if teardown:
            title += " (cleanup after the test)"
        tag, style = TAGS[outcome]
        title = title if len(title) <= 58 else title[:55] + "..."
        progress = console.paint(f"{self.done}/{self.total}", "dim")
        print(f"  {console.paint(tag, style)} {ids:<8} {title:<58} {res.get('duration', report.duration):5.1f}s  {progress}", flush=True)
        if outcome == "skipped":
            reason = report.longrepr[-1] if isinstance(report.longrepr, tuple) else str(report.longrepr or "")
            console.note(_one_line(reason.removeprefix("Skipped: ")))
        elif outcome in ("failed", "error", "rerun"):
            self._details(report, res)

    def _details(self, report, res: dict) -> None:
        pad = "         "
        if res.get("failed_step"):
            print(f"{pad}step:     {res['failed_step']}")
        if res.get("expected"):
            print(f"{pad}expected: {res['expected']}")
        message = res.get("message") or ""
        if not message:
            crash = getattr(report.longrepr, "reprcrash", None)
            lines = str(report.longrepr or "").strip().splitlines()
            message = crash.message if crash else (lines[-1] if lines else "")
        print(f"{pad}error:    {_one_line(str(message))}")
        if res.get("evidence_dir"):
            others = [n for n in ("screen.png", "page.png") if n in (res.get("evidence") or [])]
            more = f" (+ {', '.join(others)})" if others else ""
            print(f"{pad}evidence: {_short(Path(res['evidence_dir']) / 'failure.txt')}{more}", flush=True)

    # -- problems outside tests --------------------------------------------------
    def pytest_internalerror(self, excrepr) -> None:
        console.check(console.FAIL, "pytest internal error", _one_line(str(excrepr).splitlines()[-1]))

    def pytest_keyboard_interrupt(self, excinfo) -> None:
        print(console.paint("\nstopped by Ctrl+C - the results so far are in the report", console.WARN))

    def pytest_sessionfinish(self, session) -> None:
        if self.total:
            parts = [f"{n} {k}" for k, n in sorted(self.counts.items())]
            print("\n" + console.paint(f"done: {', '.join(parts) or 'nothing ran'}", "bold"), flush=True)
