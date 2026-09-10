"""Skills own their references; every command they print belongs to the tool."""

import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chromiumdiff import review
from chromiumdiff.cli import build_parser
from chromiumdiff.model import read_report, write_json
from tests.test_review import fixture


ROOT = Path(__file__).resolve().parent.parent
# How a skill is allowed to invoke the tool. There is one form, because a second
# one is where a path that only resolves from one directory gets written down.
INVOCATION = re.compile(r"python3 -m chromiumdiff (\w[\w-]*)")


def subcommands() -> set:
    actions = [a for a in build_parser()._actions if getattr(a, "choices", None)
               and isinstance(a.choices, dict)]
    return set(actions[0].choices)


class TestSkillBoundaries(unittest.TestCase):
    def test_references_resolve_without_the_other_skill(self):
        for base in (ROOT / "skills", ROOT / "docs/chromiumdiff-guide-vi"):
            skills = sorted(p.parent for p in base.glob("*/SKILL.md"))
            for skill in skills:
                with self.subTest(skill=str(skill)), tempfile.TemporaryDirectory() as tmp:
                    isolated = Path(tmp).resolve() / skill.name
                    shutil.copytree(skill, isolated)
                    for path in isolated.rglob("*"):
                        if not path.is_file() or path.suffix not in (".md", ".py", ".json"):
                            continue
                        text = path.read_text(encoding="utf-8")
                        for peer in skills:
                            if peer != skill:
                                self.assertNotIn(peer.name + "/", text, str(path))
                        for link in re.findall(r"\]\(([^)]+)\)", text):
                            if "://" in link or link.startswith("#"):
                                continue
                            target = (path.parent / link.split("#", 1)[0]).resolve()
                            self.assertTrue(target.is_file(), f"{path}: {link}")
                            self.assertIn(isolated, target.parents, f"{path}: {link}")

    def test_no_skill_tells_the_agent_to_run_a_loose_script(self):
        """A path is the thing that breaks when a file moves; a subcommand is not.

        Shared helpers once lived in one skill's own `scripts/` directory, so the
        other skill had to reach into it by path. Moving them to a repository-root
        `scripts/` fixed the reach and kept the path. They are subcommands now,
        and nothing outside `chromiumdiff/` is executable, so a skill that prints
        a script path is printing a path to a file that does not exist.
        """
        known = subcommands()
        self.assertLessEqual({"why", "cl", "review"}, known)
        for base in (ROOT / "skills", ROOT / "docs/chromiumdiff-guide-vi"):
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.suffix not in (".md", ".json"):
                    continue
                text = path.read_text(encoding="utf-8")
                rel = str(path.relative_to(ROOT))
                # assertFalse, not assertNotIn: a failure message that quotes the
                # whole file buries the name of the file that failed.
                self.assertFalse("scripts/" in text, f"{rel}: names a scripts/ path")
                loose = re.search(r"python3 \S+\.py", text)
                self.assertIsNone(loose, f"{rel}: runs a loose script {loose and loose.group()}")
                for name in INVOCATION.findall(text):
                    self.assertIn(name, known, f"{rel}: unknown subcommand {name}")

    def test_no_skill_calls_the_tool_a_script(self):
        """One word, one meaning: `script` is a Chromium launch wrapper here.

        Nothing in this repository is run as a script any more -- the commands
        are subcommands of one package. The paths were renamed and the noun was
        not, so `investigating-chromium-root-causes/SKILL.md` said both "how
        many issues the script fetches" and "Finch, enterprise policy, launch
        scripts" in one file. The second is the meaning that stays.
        """
        # The only allowed sense, in either language. The EN phrase wraps across
        # lines, so the text is joined before matching.
        allowed = re.compile(r"launch\s+scripts?|scripts?\s+khởi chạy", re.IGNORECASE)
        # Skill files only. The guide documents beside them use the word for a
        # launch or CI script outside Chromium, which is what it still means.
        skills = [d for base in (ROOT / "skills", ROOT / "docs/chromiumdiff-guide-vi")
                  for d in sorted(p.parent for p in base.glob("*/SKILL.md"))]
        self.assertEqual(len(skills), 4, "expected two skills in each language area")
        for skill in skills:
            for path in sorted(skill.rglob("*.md")):
                rel = str(path.relative_to(ROOT))
                text = allowed.sub("", path.read_text(encoding="utf-8"))
                found = re.search(r"\b[Ss]cripts?\b", text)
                self.assertIsNone(found, f"{rel}: calls the tool a script; it is "
                                         f"`python3 -m chromiumdiff <command>`")

    def test_every_reference_is_named_by_its_own_entrypoint(self):
        """A reference the entrypoint never names is one the agent never opens.

        Reachability through any chain of links is the weaker check and it
        passed while `no-row.md` was linked only from `history.md`, itself a
        conditional read -- so the one reference about an empty answer sat two
        hops behind a step the agent may skip. SKILL.md has to name each one.
        """
        for base in (ROOT / "skills", ROOT / "docs/chromiumdiff-guide-vi"):
            for entry in sorted(base.glob("*/SKILL.md")):
                with self.subTest(skill=entry.parent.name, area=base.name):
                    text = entry.read_text(encoding="utf-8")
                    named = {link.rsplit("/", 1)[-1]
                             for link in re.findall(r"\]\(([^)\s#]+)\)", text)}
                    owned = {p.name for p in (entry.parent / "reference").glob("*.md")}
                    self.assertTrue(owned, "skill has no references; the check is vacuous")
                    self.assertEqual(sorted(owned - named), [])

    def test_the_references_both_skills_carry_do_not_drift_apart(self):
        """Two copies of one procedure are two places for it to be wrong.

        The skills must work installed alone, so neither can read the other's
        files and the shared references are duplicated. Nothing held the copies
        equal: `history.md` is 155 lines in both, and a fix to one was a fix to
        one. They may differ only where a copy names a file only its own skill
        owns, which is why the comparison normalises those names away.
        """
        own_names = {"investigation.md", "review-inputs.md"}
        def normalised(path):
            text = path.read_text(encoding="utf-8")
            for name in own_names:
                text = text.replace(name, "SAVED-INPUT-REFERENCE")
            return text

        for base in (ROOT / "skills", ROOT / "docs/chromiumdiff-guide-vi"):
            skills = sorted(p.parent for p in base.glob("*/SKILL.md"))
            shared = set.intersection(*({q.name for q in (s / "reference").glob("*.md")}
                                        for s in skills))
            # handoff.md points at the other skill by name, so it differs on purpose.
            shared -= {"handoff.md"} | own_names
            self.assertTrue(shared, "no shared reference found; the comparison is vacuous")
            first, *others = skills
            for name in sorted(shared):
                for other in others:
                    with self.subTest(area=base.name, reference=name):
                        a, b = (normalised(s / "reference" / name) for s in (first, other))
                        if a == b:
                            continue
                        # The first differing line, not a 7kB diff of the file.
                        drift = next(d for d in difflib.unified_diff(
                            a.splitlines(), b.splitlines(), first.name, other.name, n=0)
                            if d[:1] in "-+" and not d.startswith(("---", "+++"))
                            and d[1:].strip())
                        self.fail(f"{name} drifted between {first.name} and {other.name}: {drift}")

    def test_shared_commands_work_with_either_skill_installed_alone(self):
        for skill in sorted((ROOT / "skills").iterdir()):
            if not (skill / "SKILL.md").is_file():
                continue
            with self.subTest(skill=skill.name), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / "workspace"
                shutil.copytree(ROOT / "chromiumdiff", workspace / "chromiumdiff",
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                shutil.copytree(skill, workspace / "skills" / skill.name)
                data = workspace / "data"
                data.mkdir()
                report, _, _, cache, report_path = fixture(data)
                finding = report.findings[0]
                finding.enrichment = {"gerrit": {"changes": [
                    {"number": 123, "match": "exact", "subject": "Update the declaration"}]}}
                write_json(report_path, report.to_dict())

                def run(*args):
                    # -E drops PYTHONPATH so only the staged copy can satisfy the
                    # import; a broken relocation cannot be masked by this checkout.
                    return subprocess.run([sys.executable, "-E", "-m", "chromiumdiff", *args],
                                          cwd=workspace, capture_output=True, text=True, timeout=20)

                result = run("why", report_path, finding.uid, "--json", "--save", "--cache", cache)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["gerrit"], finding.enrichment["gerrit"])
                self.assertEqual(read_report(report_path).findings[0].enrichment, finding.enrichment)
                missing = run("why", report_path, "no-such-identifier")
                self.assertEqual(missing.returncode, 1, missing.stderr)
                self.assertNotIn("Traceback", missing.stderr)

                probe = Path(cache) / "gerrit/probe"
                write_json(str(probe / "123.json"), {
                    "status": "MERGED", "revisions": {"commit": {"commit": {"message": "Change binding"}}}})
                write_json(str(probe / "f123.json"), {"engine/work.cc": {"lines_inserted": 1}})
                write_json(str(probe / "d123_engine_work.cc.json"), {
                    "content": [{"a": ["old_binding();"], "b": ["new_binding();"]}]})
                result = run("cl", "123", "engine/work.cc", "--cache", cache)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Change binding", result.stdout)
                self.assertIn("- old_binding();", result.stdout)
                self.assertIn("+ new_binding();", result.stdout)

    def test_a_history_command_change_is_a_tool_change_not_a_skill_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            for name in ("chromiumdiff", "skills"):
                shutil.copytree(ROOT / name, workspace / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            with patch.object(review, "__file__", str(workspace / "chromiumdiff/review.py")):
                before = review.implementation_identity()
                module = workspace / "chromiumdiff/history_cli.py"
                module.write_text(module.read_text(encoding="utf-8") + "\n# changed helper\n",
                                  encoding="utf-8")
                after = review.implementation_identity()
        self.assertNotEqual(before["tool_sha256"], after["tool_sha256"])
        self.assertEqual(before["skill_sha256"], after["skill_sha256"])


if __name__ == "__main__":
    unittest.main()
