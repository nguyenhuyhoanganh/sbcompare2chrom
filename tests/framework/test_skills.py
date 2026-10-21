"""The agent skills: valid frontmatter, links that resolve, and the Claude Code copy in sync."""
import re

import pytest

from sbtest.config import ROOT
from sbtest.tools import sync_skills

SKILLS = sorted(sync_skills.SOURCE.glob("*/SKILL.md"))


def frontmatter(path):
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert m, f"{path}: no frontmatter"
    return dict(re.findall(r"^(\w+): (.*)$", m.group(1), re.M)), path.read_text(encoding="utf-8")[m.end():]


def test_skills_found():
    assert {p.parent.name for p in SKILLS} >= {"sbtest-author", "sbtest-explore", "sbtest-intake", "sbtest-run"}


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_follows_the_standard(path):
    meta, body = frontmatter(path)
    name, desc = meta.get("name", ""), meta.get("description", "")
    assert name == path.parent.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name) and not re.search("anthropic|claude", name)
    assert 0 < len(desc) <= 1024 and not re.search(r"<[^>]+>", desc), "description: 1-1024 chars, no tags"
    assert len(body.splitlines()) < 500


def test_skill_links_resolve():
    for md in sync_skills.SOURCE.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for ref in re.findall(r"`(\.agents/skills/[^`\s]+|references/[a-z_-]+\.md|templates/[a-z_]+\.py)`", text):
            candidates = [ROOT / ref, md.parent / ref, md.parent.parent / ref]
            assert any(c.exists() for c in candidates), f"{md.relative_to(ROOT)}: {ref} does not exist"


def test_claude_copy_in_sync():
    assert not sync_skills.diff(), "run: python -m sbtest.tools.sync_skills"
