"""Turns, and the events one produces while it is still running.

A turn takes tens of seconds -- it runs commands, and one of them may ask
Gerrit -- so the reply cannot be the response to the request that started it.
It is started, it is given an id, and what it produces is collected until
somebody comes back for it.

Polling rather than a held-open response, deliberately. A chunked reply
through `BaseHTTPRequestHandler`, with the work happening in another thread
and possibly in another process, is several ways to hang a connection that
nothing then closes; a reader watching a turn can afford to ask again every
second, and a request that fails is one poll rather than the whole answer.

Nothing here knows what a model is. It owns turns, their events and the
conversations they belong to, and hands the question to whatever engine it was
given.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

from .engine import Engine, Workspace
from .session import Session, SessionStore, new_id

# Turns kept in memory. They are only the live view -- what was said is in the
# conversation on disk -- so this bounds a long session's memory rather than
# its history.
KEEP_TURNS = 40


class Turn:
    """One question being answered, and what it has produced so far."""

    def __init__(self, session_id: str, question: str) -> None:
        self.id = new_id()
        self.session_id = session_id
        self.question = question
        self.events: List[dict] = []
        self.running = True
        self.started = time.time()
        self._lock = threading.Lock()

    def add(self, event: dict) -> None:
        with self._lock:
            self.events.append(event)
            if event.get("type") == "done":
                self.running = False

    def since(self, index: int) -> dict:
        with self._lock:
            index = max(0, min(index, len(self.events)))
            return {"turn": self.id, "session": self.session_id,
                    "events": list(self.events[index:]),
                    "next": len(self.events), "running": self.running,
                    "seconds": round(time.time() - self.started, 1)}


class Chat:
    """The conversations about one report, and the turns running in them.

    One turn at a time per conversation. A second question asked while the
    first is still working would reach the engine with a history that does not
    yet contain the first answer, so it would be answered as though nothing
    had been asked -- and both answers would then be appended in whichever
    order they finished.
    """

    def __init__(self, directory: str, engine: Engine,
                 allow_shell: bool = True) -> None:
        self.workspace = Workspace(directory, allow_shell=allow_shell)
        self.engine = engine
        self.sessions = SessionStore(directory)
        self.turns: Dict[str, Turn] = {}
        self.order: List[str] = []
        self._lock = threading.Lock()
        self._busy: Dict[str, str] = {}

    def ask(self, session_id: Optional[str], question: str) -> dict:
        """Start a turn, and return what the page needs to follow it."""
        question = (question or "").strip()
        if not question:
            return {"error": "ask something"}
        session = self.sessions.get(session_id) if session_id else None
        if session is None:
            session = self.sessions.new()
        with self._lock:
            running = self._busy.get(session.id)
            if running and self.turns.get(running, None) \
                    and self.turns[running].running:
                return {"error": "this conversation is still answering",
                        "session": session.id, "turn": running}
            turn = Turn(session.id, question)
            self.turns[turn.id] = turn
            self.order.append(turn.id)
            self._busy[session.id] = turn.id
            self._forget_old()
        # Recorded before the engine runs, because the engine reads the
        # conversation to find out what was asked. An engine is never told the
        # question twice.
        session.add("user", question)
        threading.Thread(target=self._work, args=(session, turn),
                         daemon=True).start()
        return {"session": session.id, "turn": turn.id}

    def _work(self, session: Session, turn: Turn) -> None:
        try:
            self.engine.run(session, turn.question, self.workspace, turn.add)
        finally:
            # `run` promises a `done`, but a promise is not a guarantee for a
            # thread: an engine that killed the interpreter's patience some
            # other way must still not leave a reader watching for ever.
            if turn.running:
                turn.add({"type": "done"})
            self.sessions.save(session)

    def events(self, turn_id: str, since: int) -> Optional[dict]:
        turn = self.turns.get(turn_id)
        return None if turn is None else turn.since(since)

    def history(self, session_id: str) -> Optional[dict]:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        return {"session": session.id,
                "messages": [m for m in session.messages
                             if m.get("role") in ("user", "assistant")]}

    def _forget_old(self) -> None:
        while len(self.order) > KEEP_TURNS:
            self.turns.pop(self.order.pop(0), None)
