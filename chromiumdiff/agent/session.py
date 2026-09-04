"""The conversation, kept on this side rather than inside whatever answers it.

Holding the history here is the decision that makes an engine replaceable. A
backend that remembers its own conversations needs a way to name one, resume
it, and be trusted not to lose it; a backend that remembers nothing needs the
history handed to it every turn. Only the second works with both, so the
history is ours and every turn is a fresh one from the engine's point of view.

It is written to disk for the same reason the CL lookups are: a session is
minutes of somebody's questions, and losing it to a closed terminal makes the
feature worse than not having it. One file per conversation, in a `chats/`
directory beside the report, so what was asked about a report travels with it.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Dict, List, Optional

DIRECTORY = "chats"

# How much conversation goes back to the engine each turn, in characters. The
# limit is not the context window -- it is the share of the window that history
# may take before it starts crowding out the thing being asked about. A report
# question is answered from tool output, and tool output arrives fresh every
# turn; an old answer is worth less than the aggregate that would replace it.
HISTORY_BUDGET = 24000

# A tool result kept in the history costs its full length on every later turn.
# The answer written from it is what carries forward; the raw output is not.
RESULT_KEEP = 600

# How long an opening question may be and still be carried forward with every
# later turn. A question is normally a line; one longer than this is a pasted
# stack trace or a log, and repeating it on every turn for the rest of the
# conversation costs more than the anchor is worth.
OPENING_MAX = 1200


def new_id() -> str:
    """Unguessable, because it appears in a URL a browser can be told to open.

    A short counter would let any page open in the same browser walk the
    sessions on this port and read what was asked in them.
    """
    return secrets.token_urlsafe(12)


class Session:
    """One conversation: what was asked, what came back, and what ran."""

    def __init__(self, sid: Optional[str] = None,
                 messages: Optional[List[Dict[str, str]]] = None,
                 started: Optional[float] = None) -> None:
        self.id = sid or new_id()
        self.messages: List[Dict[str, str]] = messages or []
        self.started = started if started is not None else time.time()

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def for_engine(self, budget: int = HISTORY_BUDGET) -> List[Dict[str, str]]:
        """The tail of the conversation that fits, plus the question it began
        with, oldest of the rest dropped first.

        Dropped rather than summarised, because a summary is another model
        call that can be wrong -- and wrong here means a count that was never
        in the report carried forward as though it had been.

        The first question is kept because a pure tail loses what the
        conversation is *about*. "Which of those need retesting?" eight turns
        later refers to something, and the something was the opening question;
        without it the follow-up is answered against whatever happens to be
        left. It costs one message, and it cannot invent anything, which is
        the whole difference between it and a summary.

        The newest turn is always included whatever its size: sending a
        question with its context trimmed away is better than sending no
        question.
        """
        kept: List[Dict[str, str]] = []
        spent = 0
        for message in reversed(self.messages):
            content = message.get("content", "")
            if kept and spent + len(content) > budget:
                break
            kept.append(message)
            spent += len(content)
        kept.reverse()
        opening = self._opening()
        if opening is not None and opening not in kept:
            kept.insert(0, opening)
        return kept

    def _opening(self) -> Optional[Dict[str, str]]:
        """The question this conversation started with, if it is still short.

        A first question long enough to matter to the budget is one the tail
        would have had to drop for a reason, and re-adding it here would put
        the same pressure back on the turn being answered.
        """
        for message in self.messages:
            if message.get("role") == "user":
                return message if len(message.get("content", "")) <= \
                    OPENING_MAX else None
        return None

    def add_tool_result(self, name: str, text: str) -> None:
        """Record that a tool ran, without carrying its output for ever.

        The whole result is what the engine reasons from *this* turn and it
        already has it; what the next turn needs is that the tool ran and
        roughly what came back. Keeping the full text would make one large
        query the permanent cost of the rest of the conversation.
        """
        clipped = text if len(text) <= RESULT_KEEP else (
            text[:RESULT_KEEP] + f"\n[... {len(text) - RESULT_KEEP} more "
                                 f"characters, not kept in the history]")
        self.add("tool", f"{name} ->\n{clipped}")

    def to_dict(self) -> dict:
        return {"id": self.id, "started": self.started,
                "messages": self.messages}

    @classmethod
    def from_dict(cls, doc: dict) -> "Session":
        return cls(sid=doc.get("id"), messages=doc.get("messages") or [],
                   started=doc.get("started"))


class SessionStore:
    """Conversations on disk, one file each, beside the report they are about.

    Reads go through the cache rather than the disk so a turn in flight and a
    turn just finished cannot be two different conversations.
    """

    def __init__(self, directory: str) -> None:
        self.directory = os.path.join(directory, DIRECTORY)
        self._live: Dict[str, Session] = {}

    def new(self) -> Session:
        session = Session()
        self._live[session.id] = session
        return session

    def get(self, sid: str) -> Optional[Session]:
        if sid in self._live:
            return self._live[sid]
        # A session id reaches this from a URL, so it is checked against the
        # ids that exist rather than joined to a path. `../` in a session id is
        # otherwise a way to name any file on the disk.
        if sid not in self.known():
            return None
        try:
            with open(self._path(sid), encoding="utf-8") as fh:
                session = Session.from_dict(json.load(fh))
        except (OSError, ValueError):
            return None
        self._live[session.id] = session
        return session

    def save(self, session: Session) -> None:
        """Write through a temporary file, so an interrupted write loses only
        the turn that was being written and not the conversation."""
        self._live[session.id] = session
        try:
            os.makedirs(self.directory, exist_ok=True)
            tmp = self._path(session.id) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(session.to_dict(), fh)
            os.replace(tmp, self._path(session.id))
        except OSError:
            # A conversation that cannot be written is still a conversation
            # that can be had. It is in `_live` either way.
            pass

    def known(self) -> List[str]:
        try:
            return sorted(name[:-5] for name in os.listdir(self.directory)
                          if name.endswith(".json"))
        except OSError:
            return []

    def _path(self, sid: str) -> str:
        return os.path.join(self.directory, f"{sid}.json")
