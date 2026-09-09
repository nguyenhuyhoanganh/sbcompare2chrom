"""Skills own their references; executable helpers belong to the repository."""

import ast
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
from chromiumdiff.model import read_report, write_json
from tests.test_review import fixture


ROOT = Path(__file__).resolve().parent.parent


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
                        for script in re.findall(r"python3 (scripts/[\w-]+\.py)", text):
                            self.assertTrue((ROOT / script).is_file(), script)

    def test_shared_commands_work_with_either_skill_installed_alone(self):
        for skill in sorted((ROOT / "skills").iterdir()):
            if not (skill / "SKILL.md").is_file():
                continue
            with self.subTest(skill=skill.name), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / "workspace"
                for name in ("chromiumdiff", "scripts"):
                    shutil.copytree(ROOT / name, workspace / name,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                shutil.copytree(skill, workspace / "skills" / skill.name)
                data = workspace / "data"
                data.mkdir()
                report, _, _, cache, report_path = fixture(data)
                finding = report.findings[0]
                finding.enrichment = {"gerrit": {"changes": [
                    {"number": 123, "match": "exact", "subject": "Update the declaration"}]}}
                write_json(report_path, report.to_dict())

                def run(script, *args):
                    # -I and an unrelated cwd prevent the original checkout
                    # or PYTHONPATH from masking a broken relocated import.
                    return subprocess.run(
                        [sys.executable, "-I", str(workspace / "scripts" / script), *args],
                        cwd=tmp, capture_output=True, text=True, timeout=20)

                result = run("why.py", report_path, finding.uid, "--json", "--save", "--cache", cache)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["gerrit"], finding.enrichment["gerrit"])
                self.assertEqual(read_report(report_path).findings[0].enrichment, finding.enrichment)
                missing = run("why.py", report_path, "no-such-identifier")
                self.assertEqual(missing.returncode, 1, missing.stderr)
                self.assertNotIn("Traceback", missing.stderr)

                probe = Path(cache) / "gerrit/probe"
                write_json(str(probe / "123.json"), {
                    "status": "MERGED", "revisions": {"commit": {"commit": {"message": "Change binding"}}}})
                write_json(str(probe / "f123.json"), {"engine/work.cc": {"lines_inserted": 1}})
                write_json(str(probe / "d123_engine_work.cc.json"), {
                    "content": [{"a": ["old_binding();"], "b": ["new_binding();"]}]})
                result = run("cl.py", "123", "engine/work.cc", "--cache", cache)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Change binding", result.stdout)
                self.assertIn("- old_binding();", result.stdout)
                self.assertIn("+ new_binding();", result.stdout)

    def test_shared_helpers_remain_in_the_implementation_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            for name in ("chromiumdiff", "scripts", "skills"):
                shutil.copytree(ROOT / name, workspace / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            with patch.object(review, "__file__", str(workspace / "chromiumdiff/review.py")):
                before = review.implementation_identity()
                script = workspace / "scripts/why.py"
                script.write_text(script.read_text(encoding="utf-8") + "\n# changed helper\n", encoding="utf-8")
                after = review.implementation_identity()
            self.assertNotEqual(before["tool_sha256"], after["tool_sha256"])
            self.assertEqual(before["skill_sha256"], after["skill_sha256"])

    def test_shared_helpers_keep_python39_syntax_and_no_skill_paths(self):
        for script in (ROOT / "scripts").glob("*.py"):
            text = script.read_text(encoding="utf-8")
            ast.parse(text, feature_version=(3, 9))
            for skill in (ROOT / "skills").iterdir():
                self.assertNotIn(skill.name + "/", text, str(script))


if __name__ == "__main__":
    unittest.main()
