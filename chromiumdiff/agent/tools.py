"""Run one command, or one query over a report, and bound what it costs.

A model answering questions about a report needs to compute over it, and the
report is too large to hand over: `report.json` is 3.6 MB for a `default` run
and 7.2 MB for a `wide` one, which is roughly 900k and 1.8M tokens. Even every
finding stripped to the fields that identify it -- uid, kind, bucket, signals,
path -- comes to 284k tokens, still past a 200k context. So the data stays on
disk and only what a query prints comes back.

That inverts where the limit belongs. The input cannot be bounded, because a
question can be about any part of the report; the *output* can, because a
useful answer is always small. Everything here is built around bounding the
output and letting the query be whatever it needs to be.

Three failures are what the details are for:

- **`grep` does not work on a report.** `report.json` is written by
  `json.dump` with no indent, so the whole 3.6 MB is a single line. Matching
  one feature name returns the entire file as one matching line. `run_python`
  exists so the obvious tool is a parsed structure rather than a text scan.
- **A timeout that kills one process does not stop the work.** `subprocess`
  kills the direct child, and a shell that has already forked leaves the
  grandchild holding the pipe, so the read that was supposed to end at the
  timeout blocks behind it. The child gets its own process group and the
  group is what gets killed.
- **A traceback pointing at the wrong line teaches the wrong fix.** Preloading
  the report by prepending lines to the query would shift every line number in
  every traceback by the length of the preamble. The query is compiled under
  its own name instead, so line 3 of a failing query is reported as line 3.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Dict, List, Optional

# Generous, because the slowest legitimate command is a CL lookup: one row can
# read up to `serve.CLICK_BUDGET` diffs from Gerrit over the network. A limit
# tight enough to feel responsive on a query would abort the one command whose
# whole job is to be slow.
DEFAULT_TIMEOUT = 120.0

# What comes back to the model, in characters. Four thousand characters is
# about a thousand tokens, so this is roughly 3k tokens -- enough for a table,
# a hundred-odd matching rows, or a traceback, and far short of anything that
# would crowd the conversation out of the context.
DEFAULT_CAP = 12000

_READ_CHUNK = 65536

# After the group is killed, how long to wait for the reader to see EOF. It is
# a formality -- the pipe closes with the processes holding it -- but a reader
# thread that is somehow still blocked must not keep the server alive.
_REAP_GRACE = 5.0


class Result:
    """What a command did, in the shape the caller shows a model.

    `output` is stdout and stderr interleaved as the process wrote them,
    already truncated. `kept` and `dropped` are the bytes on each side of the
    cut, which is what makes truncation something the model can act on rather
    than a silent shortening: a query whose answer got cut can be narrowed,
    but only if it is told that it was cut.

    Both are **bytes**, not characters, and `output` is the decoded text, so
    `len(output)` is smaller than `kept` for anything outside ASCII. Counting
    bytes is the right unit here anyway: the cap exists to bound how much of a
    context window a tool result can take, and that tracks the encoded size.
    """

    def __init__(self, output: str, exit_code: Optional[int], dropped: int,
                 seconds: float, timed_out: bool, kept: int = 0) -> None:
        self.output = output
        self.exit_code = exit_code
        self.kept = kept
        self.dropped = dropped
        self.seconds = seconds
        self.timed_out = timed_out

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def as_text(self) -> str:
        """The whole result as the one string a model reads.

        The notes go after the output rather than before it, because a model
        reading a long result reasons from its end, and the fact that matters
        most -- this was cut, ask something narrower -- is the note.
        """
        parts: List[str] = [self.output]
        if self.timed_out:
            parts.append(
                f"[timed out after {self.seconds:.0f}s and was killed]")
        if self.dropped:
            parts.append(
                f"[output truncated: the first {self.kept} bytes of "
                f"{self.kept + self.dropped} are shown. Print a count, an "
                f"aggregate or a slice rather than the whole structure.]")
        if not self.timed_out and self.exit_code not in (0, None):
            parts.append(f"[exit code {self.exit_code}]")
        text = "\n".join(p for p in parts if p)
        return text if text.strip() else "[no output]"

    def as_dict(self) -> Dict[str, object]:
        return {"output": self.output, "exit_code": self.exit_code,
                "kept": self.kept, "dropped": self.dropped,
                "seconds": round(self.seconds, 3),
                "timed_out": self.timed_out, "ok": self.ok}


def child_env(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment a command runs in, with this package importable.

    Commands run with the report directory as their working directory, and
    from there `python3 -m chromiumdiff` fails: the package is somewhere else
    entirely. The briefing tells a reader to run exactly that -- it is how a
    row's CL is looked up, and the one thing a query cannot do for itself --
    so the instruction has to be true from where it is given rather than only
    from the directory the tool happens to live in.

    `PYTHONPATH` rather than an absolute path in the instruction, because the
    instruction is also what a person reads, and `python3 -m chromiumdiff` is
    what they would type. Prepended to whatever `PYTHONPATH` already held, so
    a caller's own path still applies after it.

    Works from a `.pyz` too: `__file__` inside a zipapp is a path *through*
    the archive, so two directories up from the package is the archive
    itself -- and Python imports from one of those directly.
    """
    env = dict(os.environ if base is None else base)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(root)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (root + os.pathsep + existing) if existing else root
    return env


def _kill_tree(proc: "subprocess.Popen") -> None:
    """Kill the child and anything it started, and never anything else.

    A shell command is the usual case and a shell forks, so killing the pid
    that `Popen` returns can leave the real work running -- and holding the
    pipe this module is reading, which is the part that matters: the read ends
    when the last writer closes, not when the first one dies.

    The group is checked against this process's own before it is signalled.
    Without that check the failure is far worse than the one being fixed: a
    child started without `start_new_session` is in *our* group, so asking the
    kernel for "the child's group" returns the group holding the server, and
    the timeout would SIGKILL the whole session -- the server, the caller, and
    the terminal it was started from. It is one line, and it is the difference
    between a timeout that stops a command and a timeout that stops the tool.
    """
    if os.name == "posix":
        try:
            group = os.getpgid(proc.pid)
            if group != os.getpgid(0):
                os.killpg(group, signal.SIGKILL)
                return
        except (OSError, AttributeError):
            # The group is already gone, or this platform lied about having
            # process groups. Fall through to the single-process kill, which
            # is worse but is what is left.
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _drain(stream, cap: int, into: Dict[str, object]) -> None:
    """Read to EOF, keeping the first `cap` bytes and counting the rest.

    Reading everything and truncating afterwards would hold a gigabyte in
    memory to show 12 kB of it. Stopping the read at the cap instead is worse:
    the child blocks writing into a full pipe and stays alive until the
    timeout, so a query that printed too much is reported as one that hung.
    Neither is what happened. Keeping the head and discarding the tail costs
    only the time to read it, and the count of what was discarded is what the
    model needs.
    """
    kept: List[bytes] = []
    kept_len = 0
    dropped = 0
    while True:
        try:
            chunk = stream.read(_READ_CHUNK)
        except (ValueError, OSError):
            # The stream was closed under us, which is what killing the group
            # does. Whatever was read before that is still the answer.
            break
        if not chunk:
            break
        room = cap - kept_len
        if room > 0:
            kept.append(chunk[:room])
            kept_len += min(room, len(chunk))
            dropped += max(0, len(chunk) - room)
        else:
            dropped += len(chunk)
    into["bytes"] = b"".join(kept)
    into["dropped"] = dropped


def run_shell(command: str, cwd: str, timeout: float = DEFAULT_TIMEOUT,
              cap: int = DEFAULT_CAP,
              env: Optional[Dict[str, str]] = None) -> Result:
    """Run `command` through the shell in `cwd`, bounded by `timeout` and `cap`.

    stderr is merged into stdout rather than reported beside it, so a
    traceback arrives at the point in the output where it happened. Split
    apart they have to be re-interleaved by whoever reads them, and the usual
    guess -- output first, errors after -- is wrong for every command that
    fails halfway.

    The environment is inherited. This runs on the machine of the person who
    started the server and answers only to them; a deployment serving other
    people is a different question, and the place to answer it is here.
    """
    return _run(["/bin/sh", "-c", command] if os.name == "posix"
                else ["cmd", "/c", command],
                cwd=cwd, timeout=timeout, cap=cap, env=env)


def run_python(code: str, cwd: str, report_path: Optional[str] = None,
               timeout: float = DEFAULT_TIMEOUT, cap: int = DEFAULT_CAP,
               env: Optional[Dict[str, str]] = None) -> Result:
    """Run `code` with the report already loaded, and return what it printed.

    `R` is the parsed `report.json` and `F` is `R["findings"]`, both bound
    before the query runs. Loading costs 0.01s for a `default` report and
    0.03s for a `wide` one, measured on M148 -> M151, so there is nothing to
    gain by caching it between calls and a stale copy to lose.

    They are bound rather than documented because the alternative is a query
    spending its first attempt discovering the path, the encoding and the key
    the findings live under -- three round trips through a model to arrive
    where every query was going to start.
    """
    workdir = tempfile.mkdtemp(prefix="chromiumdiff-query-")
    try:
        query_path = os.path.join(workdir, "query.py")
        with open(query_path, "w", encoding="utf-8") as fh:
            fh.write(code)
        driver_path = os.path.join(workdir, "driver.py")
        with open(driver_path, "w", encoding="utf-8") as fh:
            fh.write(_driver(query_path, report_path))
        return _run([sys.executable, driver_path], cwd=cwd, timeout=timeout,
                    cap=cap, env=env)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _driver(query_path: str, report_path: Optional[str]) -> str:
    """The program that loads the report and runs the query under its own name.

    `compile(src, "<query>", "exec")` is the whole point: it makes every line
    number in every traceback a line number in the text the model wrote. The
    driver's own frame is then dropped from the traceback, because a model
    shown a frame inside machinery it cannot see will try to fix it.
    """
    return _DRIVER.format(query=repr(query_path), report=repr(report_path))


_DRIVER = '''\
import json
import sys
import traceback
from collections import Counter, defaultdict

_report = {report}
R = None
F = []
if _report:
    with open(_report, encoding="utf-8") as _fh:
        R = json.load(_fh)
    F = R.get("findings", []) if isinstance(R, dict) else []

with open({query}, encoding="utf-8") as _fh:
    _src = _fh.read()

_env = {{"R": R, "F": F, "json": json, "Counter": Counter,
         "defaultdict": defaultdict, "__name__": "__main__"}}
try:
    exec(compile(_src, "<query>", "exec"), _env)
except SystemExit:
    raise
except BaseException:
    _type, _value, _tb = sys.exc_info()
    # `_tb.tb_next` skips this frame, so the traceback starts in the query.
    traceback.print_exception(_type, _value, _tb.tb_next if _tb else None)
    sys.exit(1)
'''


def _run(argv: List[str], cwd: str, timeout: float, cap: int,
         env: Optional[Dict[str, str]]) -> Result:
    """Start, read with a cap, and stop at the timeout by killing the group."""
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
            # POSIX only, and guarded rather than passed blindly: it is what
            # gives the child a group of its own, which is what makes the
            # timeout able to stop the work rather than one process of it.
            start_new_session=(os.name == "posix"))
    except OSError as exc:
        return Result(f"[could not start: {exc}]", None, 0,
                      time.monotonic() - started, False)

    into: Dict[str, object] = {"bytes": b"", "dropped": 0}
    reader = threading.Thread(target=_drain, args=(proc.stdout, cap, into),
                              daemon=True)
    reader.start()
    reader.join(timeout)
    timed_out = reader.is_alive()
    if timed_out:
        _kill_tree(proc)
        reader.join(_REAP_GRACE)

    try:
        proc.wait(timeout=_REAP_GRACE)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
    try:
        if proc.stdout is not None:
            proc.stdout.close()
    except OSError:
        pass

    raw = into.get("bytes") or b""
    if not isinstance(raw, bytes):
        raw = str(raw).encode("utf-8")
    # The cut lands on a byte boundary, so the last character can be half of
    # one. `replace` turns that half into U+FFFD rather than raising, which
    # costs one visible glyph and saves the whole result.
    text = raw.decode("utf-8", errors="replace")
    return Result(text, proc.returncode, int(into.get("dropped") or 0),
                  time.monotonic() - started, timed_out, kept=len(raw))
