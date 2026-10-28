"""The agent skills (.agents/skills, Agent Skills format): valid frontmatter, links that resolve."""
import re

import pytest
import yaml

from sbtest.config import ROOT

SOURCE = ROOT / ".agents" / "skills"
SKILLS = sorted(SOURCE.glob("*/SKILL.md"))


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: no frontmatter"
    # parse it as YAML like the agents do: an unquoted ": " in the description breaks the
    # mapping and the agent silently loses the description (the skill is then not triggered)
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        pytest.fail(f"{path}: frontmatter is not valid YAML ({str(e).splitlines()[0]}); quote the value or drop ': '")
    assert isinstance(meta, dict), f"{path}: frontmatter must be a mapping"
    return meta, text[m.end():]


def test_skills_found():
    assert {p.parent.name for p in SKILLS} >= {"sbtest-author", "sbtest-explore", "sbtest-intake", "sbtest-run"}


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_follows_the_standard(path):
    meta, body = frontmatter(path)
    name, desc = meta.get("name", ""), meta.get("description", "")
    assert name == path.parent.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name), "name: lower-case letters, digits and -, 1-64 chars"
    assert 0 < len(desc) <= 1024 and not re.search(r"<[^>]+>", desc), "description: 1-1024 chars, no tags"
    assert len(body.splitlines()) < 500


def test_skill_links_resolve():
    for md in SOURCE.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for ref in re.findall(r"`(\.agents/skills/[^`\s]+|references/[a-z_-]+\.md|templates/[a-z_]+\.py)`", text):
            candidates = [ROOT / ref, md.parent / ref, md.parent.parent / ref]
            assert any(c.exists() for c in candidates), f"{md.relative_to(ROOT)}: {ref} does not exist"

