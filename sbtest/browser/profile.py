"""Fresh, isolated user-data-dir per browser session, optionally pre-seeded.

Seeding happens *before* the browser starts (files are read at startup):
    profile.prefs({...})            -> Default/Preferences (merged)
    profile.bookmarks(seed)         -> Default/Bookmarks
    profile.copy_from(template_dir) -> any ready-made profile (e.g. resources/profiles/<name>)
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
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


# Chromium writes files ~110 characters deep inside a profile (IndexedDB, Service Worker
# caches, extension settings) and does not use Windows long paths: a profile folder longer
# than this makes the browser show "Profile error occurred" and stop answering WebDriver.
MAX_PROFILE_DIR = 140   # 149 worked, 236 failed (Samsung 31): keep a margin
SHORT_ROOT = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "sbtest" / "profiles"


def profiles_root(preferred: Path) -> Path:
    """``preferred`` (next to the run output), or a short folder when the repo lives so deep
    that profile files would pass Windows' 260-character path limit."""
    longest = len(str(Path(preferred).resolve())) + 1 + 30 + 7     # + "\" + name (30) + "_xxxxxx"
    return Path(preferred) if longest <= MAX_PROFILE_DIR else SHORT_ROOT


class Profile:
    def __init__(self, base_dir: Path, name: str = "") -> None:
        self.dir = profiles_root(base_dir) / unique(slug(name or "profile", 30))
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
