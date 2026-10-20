"""Fresh, isolated user-data-dir per browser session, optionally pre-seeded.

Seeding happens *before* the browser starts (files are read at startup):
    profile.prefs({...})            -> Default/Preferences (merged)
    profile.bookmarks(seed)         -> Default/Bookmarks
    profile.copy_from(template_dir) -> any ready-made profile (e.g. test_data/profiles/<name>)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from sbtest.config import deep_merge
from sbtest.data.bookmarks import BookmarksSeed
from sbtest.utils import slug, unique


def expand_dotted(prefs: dict) -> dict:
    """``{"download.prompt_for_download": False}`` -> ``{"download": {"prompt_for_download": False}}``."""
    out: dict = {}
    for key, value in prefs.items():
        cur = out
        parts = key.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        if isinstance(value, dict):
            value = expand_dotted(value)
        cur[parts[-1]] = deep_merge(cur.get(parts[-1], {}), value) if isinstance(value, dict) else value
    return out


class Profile:
    def __init__(self, base_dir: Path, name: str = "") -> None:
        self.dir = Path(base_dir) / unique(slug(name or "profile", 60))
        self.default = self.dir / "Default"
        self.downloads = self.dir / "_downloads"
        self.default.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        # Marks first run as done: suppresses welcome / first-run UI.
        (self.dir / "First Run").write_text("")

    # -- seeding ---------------------------------------------------------------
    def prefs(self, prefs: dict) -> "Profile":
        f = self.default / "Preferences"
        current = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        f.write_text(json.dumps(deep_merge(current, expand_dotted(prefs)), indent=2), encoding="utf-8")
        return self

    def bookmarks(self, seed: BookmarksSeed | dict) -> "Profile":
        if isinstance(seed, dict):
            seed = BookmarksSeed.from_dict(seed)
        seed.write(self.default / "Bookmarks")
        return self

    def copy_from(self, template: Path) -> "Profile":
        shutil.copytree(template, self.dir, dirs_exist_ok=True)
        return self

    def remove(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
