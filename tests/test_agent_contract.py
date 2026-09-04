"""What an engine has to do, written as tests rather than as a description.

This file is the specification of the seam. An implementation that passes it
works with the server, the page and the conversation store; one that does not
will fail here rather than in front of a reader, which is the whole reason it
exists.

To check an implementation, subclass `EngineContract`, return one from
`make_engine`, and run this module. The rules are few and each is here because
breaking it produces a specific failure, named in the test.

`ContractCatchesViolationsTest` at the bottom runs the contract against engines
that break each rule on purpose. Without it a contract that had quietly stopped
checking anything would look exactly like an implementation that was correct.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromiumdiff.agent import engine as engine_mod
from chromiumdiff.agent.session import Session


def workspace_in(directory):
    """A report directory with enough in it to answer a question about."""
    findings = [{"change": {"change_type": "modified", "kind": "mojo_field",
                            "key": "blink.mojom.Params.early_hints",
                            "name": "early_hints",
                            "signals": ["ipc_shape_changed"], "severity": 80},
                 "reasons": ["severity 80"], "score": 80,
                 "bucket": "breaking"}]
    with open(os.path.join(directory, "report.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"from_ref": "M148", "to_ref": "M151", "findings": findings,
                   "summary": {"total": 1},
                   "meta": {"platform": "windows", "target_set": "default"}},
                  fh)
    return engine_mod.Workspace(directory)


class EngineContract:
    """The rules. Subclass with `make_engine` and run.

    The harness -- the server, or a test -- puts the reader's question into
    the session before calling `run`. An engine reads the conversation from
    `session.for_engine()` and appends its own answer; it does not record the
    question, because by the time it is called the question is already there.
    """

    QUESTION = "How many Breaking findings are there?"

    def make_engine(self):
        raise NotImplementedError

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="chromiumdiff-contract-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.workspace = workspace_in(self.dir)
        self.session = Session()
        self.session.add("user", self.QUESTION)
        self.events = []

    def _answer(self, question=None):
        engine = self.make_engine()
        engine.run(self.session, question or self.QUESTION, self.workspace,
                   self.events.append)
        return self.events

    def test_a_turn_ends_exactly_once(self):
        """A reader is watching. A turn that does not end never stops.

        `done` is what takes the spinner off the screen, and a second one
        would end a turn that had already been replaced.
        """
        events = self._answer()
        endings = [e for e in events if e["type"] == "done"]
        self.assertEqual(1, len(endings), "a turn must end exactly once")
        self.assertIs(endings[0], events[-1], "`done` must be last")

    def test_every_event_is_one_the_page_can_render(self):
        for event in self._answer():
            self.assertIn("type", event)
            self.assertIn(event["type"], engine_mod.EVENT_TYPES, event)

    def test_a_turn_says_something(self):
        """Silence and failure look identical to whoever asked."""
        kinds = {e["type"] for e in self._answer()}
        self.assertTrue(kinds & {"text", "error"},
                        "a turn must produce prose or say why it could not")

    def test_a_tool_call_is_followed_by_what_it_returned(self):
        """The page shows the command, then what it printed.

        A command shown with no result reads as one that is still running,
        for ever.
        """
        events = self._answer()
        for index, event in enumerate(events):
            if event["type"] != "tool":
                continue
            self.assertLess(index + 1, len(events),
                            "a tool call must be followed by its result")
            after = events[index + 1]
            self.assertEqual("tool_result", after["type"])
            self.assertEqual(event["name"], after["name"])

    def test_a_tool_call_names_a_tool_and_carries_its_input(self):
        for event in self._answer():
            if event["type"] == "tool":
                self.assertTrue(event.get("name"))
                self.assertIsInstance(event.get("input"), str)

    def test_the_answer_is_kept_in_the_conversation(self):
        """The next turn is answered from the history, so it has to be there.

        An engine that emits an answer and does not record it produces a
        conversation where every question is the first one.
        """
        events = self._answer()
        if not [e for e in events if e["type"] == "text"]:
            self.skipTest("this engine produced no prose to record")
        self.assertEqual("assistant", self.session.messages[-1]["role"])
        self.assertTrue(self.session.messages[-1]["content"].strip())

    def test_the_question_is_not_recorded_twice(self):
        """The harness put it there. An engine adding it again doubles it."""
        self._answer()
        asked = [m for m in self.session.messages
                 if m["role"] == "user" and m["content"] == self.QUESTION]
        self.assertEqual(1, len(asked))

    def test_a_failing_engine_reports_rather_than_raises(self):
        """A raised exception takes down a server holding a conversation."""
        broken = self.make_engine()
        broken._run = _explode
        events = []
        broken.run(self.session, self.QUESTION, self.workspace, events.append)
        self.assertEqual("done", events[-1]["type"])
        self.assertTrue([e for e in events if e["type"] == "error"])

    def test_nothing_arrives_after_the_turn_has_ended(self):
        late = self.make_engine()
        late._run = _emit_after_done
        events = []
        late.run(self.session, self.QUESTION, self.workspace, events.append)
        self.assertEqual("done", events[-1]["type"])
        self.assertNotIn("late", [e.get("text") for e in events])


def _explode(session, question, workspace, emit):
    raise RuntimeError("the endpoint refused")


def _emit_after_done(session, question, workspace, emit):
    emit(engine_mod.text("first"))
    emit(engine_mod.done())
    emit(engine_mod.text("late"))


class ScriptedEngineContract(EngineContract, unittest.TestCase):
    """The reference implementation, run against its own specification."""

    def make_engine(self):
        return engine_mod.ScriptedEngine([
            "<run-python>\n"
            "print(sum(1 for f in F if f['bucket'] == 'breaking'))\n"
            "</run-python>",
            "One Breaking finding: mojo_field:blink.mojom.Params.early_hints, "
            "an ipc_shape_changed at severity 80.",
        ])


class HttpEngineContract(EngineContract, unittest.TestCase):
    """The HTTP engine, with the endpoint replaced and nothing else.

    It runs the same loop, parses the same tags and executes the same tools,
    so everything except the request itself is under test here.
    """

    def make_engine(self):
        replies = iter([
            "<run-python>\nprint(len(F))\n</run-python>",
            "There is one finding, and it is Breaking.",
        ])

        class _Local(engine_mod.HttpEngine):
            def complete(self, messages):
                return next(replies, "done")

        return _Local(base_url="http://example.invalid", model="test")


class ContractCatchesViolationsTest(unittest.TestCase):
    """The contract is only worth running if a broken engine fails it.

    Each engine below breaks exactly one rule. If the contract passes any of
    them it has stopped checking that rule, and an implementation handed over
    against it would inherit the gap.
    """

    def _verdict(self, engine_factory):
        case = type("Case", (EngineContract, unittest.TestCase),
                    {"make_engine": lambda self: engine_factory()})
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
        result = unittest.TestResult()
        suite.run(result)
        return result

    def test_the_contract_passes_the_reference_engine(self):
        result = self._verdict(lambda: engine_mod.ScriptedEngine([
            "<run-python>\nprint(len(F))\n</run-python>", "One finding."]))
        self.assertEqual([], result.failures + result.errors)
        self.assertGreater(result.testsRun, 5)

    def test_an_engine_that_never_ends_is_caught(self):
        self.assertTrue(self._verdict(_Silent).failures)

    def test_an_engine_that_shows_a_command_and_no_result_is_caught(self):
        self.assertTrue(self._verdict(_Orphan).failures)

    def test_an_engine_that_forgets_its_answer_is_caught(self):
        self.assertTrue(self._verdict(_Forgetful).failures)

    def test_an_engine_that_repeats_the_question_is_caught(self):
        self.assertTrue(self._verdict(_Repeats).failures)


class _Silent(engine_mod.Engine):
    """Ends the turn twice, which is one more ending than a reader can use."""

    def run(self, session, question, workspace, emit):  # bypasses `guard`
        emit(engine_mod.text("hello"))
        emit(engine_mod.done())
        emit(engine_mod.done())


class _Orphan(engine_mod.Engine):
    def _run(self, session, question, workspace, emit):
        emit(engine_mod.tool("python", "print(1)"))
        emit(engine_mod.text("done looking"))
        session.add("assistant", "done looking")


class _Forgetful(engine_mod.Engine):
    def _run(self, session, question, workspace, emit):
        emit(engine_mod.text("Four Breaking findings."))


class _Repeats(engine_mod.Engine):
    def _run(self, session, question, workspace, emit):
        session.add("user", question)
        emit(engine_mod.text("ok"))
        session.add("assistant", "ok")


if __name__ == "__main__":
    unittest.main()
