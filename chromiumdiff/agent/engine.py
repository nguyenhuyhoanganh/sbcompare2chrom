"""The one seam between this tool and whatever model answers a question.

An engine is handed a question, a workspace and a way to emit events, and is
responsible for producing an answer. Everything else -- the conversation, the
report, the bounded runner, the page -- is on this side of the seam and does
not change when the engine does.

The seam is drawn here rather than at "send these messages, get a reply"
because the two engines that matter sit on opposite sides of that line. A
plain completion endpoint has no loop of its own and needs one written around
it; a coding agent already is a loop and would have to be dismantled to fit
inside another one. Asking both for *an answer to a question* is the only
request they can both take.

What an engine must not do is raise. A question that cannot be answered is an
answer -- `error` is an event like any other -- and an exception crossing this
boundary takes down a server that is holding somebody else's conversation.
`guard` wraps a `run` so that this holds even when the implementation forgets.

## Implementing one

Subclass `Engine`, set `name`, and write two methods:

    def available(self):    # "" if this engine can run, else why it cannot
    def _run(self, session, question, workspace, emit):

`_run` calls `emit(...)` with the events below as it goes, and returns when the
answer is complete. It must not emit `done`; `guard` does that, exactly once,
whatever happens inside.

Then run the contract tests against it. They are the specification:

    python3 -m unittest tests.test_agent_contract
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

from ..model import Report
from . import briefing
from .tools import DEFAULT_CAP, DEFAULT_TIMEOUT, Result, run_python, run_shell

Emit = Callable[[dict], None]

# How many tools one question may run before the answer has to be written from
# what is already known. A question about a report is a handful of queries; a
# loop that has run a dozen is not converging, and the reader is better served
# by what it has than by watching it continue.
MAX_STEPS = 12

# The whole turn, in seconds. Separate from the per-command timeout: twelve
# commands each finishing just inside their own limit is not an answer anyone
# is still waiting for.
TURN_SECONDS = 300.0

# The protocol. A tag rather than a native tool-calling API, because native
# tool calling is the part of an endpoint's shape most likely to differ, and
# this has to work against one whose shape is not known. Written once and used
# by both the prompt and the parser, so the two cannot describe different
# protocols.
TAGS = {"run-python": "python", "run-shell": "shell"}

_CALL_RE = re.compile(
    r"<(" + "|".join(TAGS) + r")>\s*\n?(.*?)\n?\s*</\1>", re.S)


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def tool(name: str, source: str) -> dict:
    return {"type": "tool", "name": name, "input": source}


def tool_result(name: str, result: Result) -> dict:
    return {"type": "tool_result", "name": name, "output": result.as_text(),
            "ok": result.ok, "seconds": round(result.seconds, 2)}


def error(message: str) -> dict:
    return {"type": "error", "message": message}


def done() -> dict:
    return {"type": "done"}


EVENT_TYPES = ("text", "tool", "tool_result", "error", "done")


class Workspace:
    """The report an engine is answering about, and the only ways to reach it.

    Commands run with the report directory as the working directory, which is
    what makes every path an engine writes a short one and what makes the
    briefing's instructions true as written.
    """

    def __init__(self, directory: str, allow_shell: bool = True,
                 timeout: float = DEFAULT_TIMEOUT,
                 cap: int = DEFAULT_CAP) -> None:
        self.directory = os.path.abspath(directory)
        self.allow_shell = allow_shell
        self.timeout = timeout
        self.cap = cap

    @property
    def report_path(self) -> str:
        return os.path.join(self.directory, "report.json")

    def run(self, name: str, source: str) -> Result:
        if name == "python":
            return run_python(source, cwd=self.directory,
                              report_path=self.report_path,
                              timeout=self.timeout, cap=self.cap)
        if name == "shell":
            if not self.allow_shell:
                return Result("[shell is not available here. Everything about "
                              "the report can be answered with python.]",
                              1, 0, 0.0, False)
            return run_shell(source, cwd=self.directory, timeout=self.timeout,
                             cap=self.cap)
        return Result(f"[no tool called {name!r}]", 1, 0, 0.0, False)

    def briefing_text(self) -> str:
        """What the report says about itself.

        Read from `AGENTS.md` when it is there, so a note somebody has edited
        is the note that gets used, and rendered from the report when it is
        not -- an old report directory predates the file and still has to work.
        """
        path = briefing.path_in(self.directory)
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            pass
        try:
            with open(self.report_path, encoding="utf-8") as fh:
                return briefing.render(Report.from_dict(json.load(fh)),
                                       self.directory)
        except (OSError, ValueError, KeyError):
            return ""

    def system_prompt(self) -> str:
        tools = "\n".join(
            f"<{tag}>\n...\n</{tag}>" for tag, name in TAGS.items()
            if name != "shell" or self.allow_shell)
        return _SYSTEM.format(briefing=self.briefing_text(), tools=tools,
                              steps=MAX_STEPS)


_SYSTEM = """\
You answer questions about one Chromium comparison report, for a reader who \
may be an engineer or may not. Match them: a question naming a flag gets a \
technical answer, a question about "what changed in settings" gets one a \
tester can act on. Say which you are doing when it is not obvious.

Cite what you claim. A finding has a uid, a path and a line; an answer that \
names them can be checked, and one that does not cannot. Where the report \
does not settle something, say that rather than closing the gap yourself.

To look something up, write one of these and stop. The result comes back and \
you continue:

{tools}

Use at most {steps} of them for one question. Print aggregates and slices, \
never whole structures. When you have the answer, write it with no tag.

Everything below is the report's own description of itself.

{briefing}"""


class Engine:
    """What answers a question. Subclass, set `name`, write `_run`."""

    name = "engine"

    def available(self) -> str:
        """"" if this engine can run here, otherwise why it cannot."""
        return ""

    def run(self, session, question: str, workspace: Workspace,
            emit: Emit) -> None:
        """Answer `question`, emitting events. Never raises, always ends."""
        guard(self._run, session, question, workspace, emit)

    def _run(self, session, question: str, workspace: Workspace,
             emit: Emit) -> None:
        raise NotImplementedError


def guard(run, session, question: str, workspace: Workspace,
          emit: Emit) -> None:
    """Run an engine so the caller gets exactly one ending, whatever happens.

    Two failures are covered and they are opposite. An engine that raises
    would otherwise leave a reader watching a spinner for ever, so the
    exception becomes an `error` event. An engine that emits after finishing
    would otherwise append to a conversation that has already been answered,
    so `emit` stops accepting events once `done` has gone out.

    The gate closes when a `done` passes through, not when `run` returns.
    Closing it on the return was the same bug in a quieter form: an engine
    that ended its own turn and then kept talking was still inside `run`, so
    every later event went straight out and the turn ended twice.
    """
    finished = [False]

    def once(event: dict) -> None:
        if finished[0]:
            return
        emit(event)
        if event.get("type") == "done":
            finished[0] = True

    try:
        run(session, question, workspace, once)
    except Exception as exc:  # an engine failing is an answer, not a crash
        once(error(f"{type(exc).__name__}: {exc}"))
    finally:
        once(done())


class TextProtocolEngine(Engine):
    """The loop around an endpoint that has no loop of its own.

    Subclasses supply `complete(messages)` and nothing else. The tags in the
    reply are what drive the loop, so this works against any endpoint that can
    return text -- which is the point, since the shape of the one it will run
    against is not known here.
    """

    name = "text-protocol"

    def complete(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError

    def _run(self, session, question: str, workspace: Workspace,
             emit: Emit) -> None:
        deadline = time.monotonic() + TURN_SECONDS
        messages = [{"role": "system", "content": workspace.system_prompt()}]
        messages.extend(session.for_engine())
        answered: List[str] = []

        for step in range(MAX_STEPS + 1):
            if time.monotonic() > deadline:
                emit(error(f"gave up after {TURN_SECONDS:.0f}s"))
                break
            reply = self.complete(messages)
            calls = _CALL_RE.findall(reply or "")
            prose = _CALL_RE.sub("", reply or "").strip()
            if prose:
                emit(text(prose))
                answered.append(prose)
            if not calls:
                break
            if step == MAX_STEPS:
                # Said to the engine, not only to the reader: the next reply
                # is the answer, and it has to know that before writing it.
                emit(error(f"stopped after {MAX_STEPS} lookups"))
                break
            messages.append({"role": "assistant", "content": reply})
            for tag, source in calls:
                name = TAGS[tag]
                emit(tool(name, source))
                result = workspace.run(name, source)
                emit(tool_result(name, result))
                session.add_tool_result(name, result.as_text())
                messages.append({"role": "user",
                                 "content": f"<result>\n{result.as_text()}\n"
                                            f"</result>"})
        if answered:
            session.add("assistant", "\n\n".join(answered))


class HttpEngine(TextProtocolEngine):
    """An OpenAI-shaped chat endpoint, reached with the standard library.

    The request shape is a guess and is meant to be one: it is the most common
    shape, it is in one method, and an endpoint that wants a different one is
    a subclass overriding `complete`. Nothing above this line knows what a
    request looks like.
    """

    name = "http"

    def __init__(self, base_url: str = "", model: str = "",
                 api_key: str = "", timeout: float = 120.0) -> None:
        self.base_url = (base_url
                         or os.environ.get("CHROMIUMDIFF_MODEL_URL", "")
                         ).rstrip("/")
        self.model = model or os.environ.get("CHROMIUMDIFF_MODEL", "")
        self.api_key = api_key or os.environ.get("CHROMIUMDIFF_API_KEY", "")
        self.timeout = timeout

    def available(self) -> str:
        if not self.base_url:
            return ("no endpoint configured -- set CHROMIUMDIFF_MODEL_URL, "
                    "or use an engine that carries its own")
        return ""

    def complete(self, messages: List[Dict[str, str]]) -> str:
        payload = json.dumps({"model": self.model, "messages": messages,
                              "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload,
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.api_key}"}
                        if self.api_key else {})})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The body, not just the status: an endpoint refusing a request
            # says why in it, and "400" alone sends the reader to the wrong
            # question.
            body = exc.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"{exc.code} from the endpoint: {body}")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"could not reach the endpoint: {exc}")
        try:
            return doc["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(
                f"the endpoint answered in a shape this does not read: "
                f"{json.dumps(doc)[:300]}")


class ScriptedEngine(Engine):
    """An engine whose replies are decided in advance, for tests.

    It goes through the same loop as a real one -- the tags in its replies are
    parsed, the tools they name really run, the results really come back -- so
    a test using it exercises everything except the network.
    """

    name = "scripted"

    def __init__(self, replies: List[str]) -> None:
        self.replies = list(replies)
        self.seen: List[List[Dict[str, str]]] = []

    def _run(self, session, question: str, workspace: Workspace,
             emit: Emit) -> None:
        loop = _Scripted(self)
        loop._run(session, question, workspace, emit)


class _Scripted(TextProtocolEngine):

    def __init__(self, owner: ScriptedEngine) -> None:
        self.owner = owner

    def complete(self, messages: List[Dict[str, str]]) -> str:
        self.owner.seen.append(list(messages))
        if not self.owner.replies:
            return "I have nothing further."
        return self.owner.replies.pop(0)


class ClineEngine(Engine):
    """Hand the question to a coding agent that already has its own loop.

    **This is the part left to be written**, and it is deliberately the only
    part. Everything it needs is already here: `workspace.directory` is where
    the report lives, `workspace.briefing_text()` is what to tell it about the
    report, and `session.for_engine()` is the conversation so far, in order.

    What an implementation has to do:

    1. Start the agent with `workspace.directory` as its working directory.
       The briefing is already written there as `AGENTS.md`, which several
       agents read on their own; if this one does not, pass
       `workspace.briefing_text()` as its instructions.
    2. Give it the conversation. `session.for_engine()` returns the turns that
       fit, oldest first, each a `{"role", "content"}` dict. Do not rely on
       the agent remembering a previous turn -- the history is kept here
       precisely so that it does not have to.
    3. Emit as it goes: `text(...)` for prose, `tool(name, source)` before a
       command it runs and `tool_result(name, result)` after. A turn that
       emits only at the end works, and reads as a hang for however long it
       takes.
    4. Append the final answer with `session.add("assistant", ...)`.
    5. Do not emit `done` and do not raise. `guard` handles both.

    The contract tests in `tests/test_agent_contract.py` check every one of
    these. An implementation that passes them works with the rest of this.
    """

    name = "cline"

    def __init__(self, program: str = "cline") -> None:
        self.program = program

    def available(self) -> str:
        return (f"{self.program} is not wired up yet -- see ClineEngine in "
                f"chromiumdiff/agent/engine.py for what it has to do")

    def _run(self, session, question: str, workspace: Workspace,
             emit: Emit) -> None:
        emit(error(self.available()))


def build(name: str = "", **kwargs) -> Engine:
    """The engine asked for, or the one that says why it cannot run."""
    engines = {"http": HttpEngine, "cline": ClineEngine}
    if name and name not in engines:
        raise ValueError(f"no engine called {name!r}; "
                         f"try one of {', '.join(sorted(engines))}")
    return engines.get(name, HttpEngine)(**kwargs)
