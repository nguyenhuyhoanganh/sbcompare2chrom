"""Build a Chromium ``Bookmarks`` file to pre-seed a profile before launch.

Seeding through the file is much faster and more deterministic than clicking through
the UI. Use it for *preconditions*; use the UI only for the step under test.

    seed = (BookmarksSeed()
            .url("Example", "https://example.com")
            .folder("Work", [Bm("Docs", "http://127.0.0.1/docs"), Folder("Empty")])
            .url("Other one", "https://other.test", root="other"))
    seed.write(profile_dir / "Default" / "Bookmarks")
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT_NAMES = {"bookmark_bar": "Bookmarks bar", "other": "Other bookmarks", "synced": "Mobile bookmarks"}


def _chrome_time() -> str:
    # microseconds since 1601-01-01 (Windows FILETIME epoch), as Chromium stores it
    return str(int((time.time() + 11644473600) * 1_000_000))


@dataclass
class Bm:
    name: str
    url: str


@dataclass
class Folder:
    name: str
    children: list = field(default_factory=list)


class BookmarksSeed:
    def __init__(self) -> None:
        self.roots: dict[str, list] = {k: [] for k in ROOT_NAMES}

    def url(self, name: str, url: str, root: str = "bookmark_bar") -> "BookmarksSeed":
        self.roots[root].append(Bm(name, url))
        return self

    def folder(self, name: str, children: list | None = None, root: str = "bookmark_bar") -> "BookmarksSeed":
        self.roots[root].append(Folder(name, list(children or [])))
        return self

    def extend(self, items: list, root: str = "bookmark_bar") -> "BookmarksSeed":
        self.roots[root].extend(items)
        return self

    @classmethod
    def from_dict(cls, data: dict) -> "BookmarksSeed":
        """From YAML-like data: ``{bookmark_bar: [{name, url} | {name, children: [...]}], other: [...]}``."""

        def conv(item: dict):
            if "url" in item:
                return Bm(item["name"], item["url"])
            return Folder(item["name"], [conv(c) for c in item.get("children", [])])

        seed = cls()
        for root, items in data.items():
            seed.roots[root] = [conv(i) for i in items or []]
        return seed

    def to_json(self) -> dict:
        next_id = [4]  # 1..3 are the permanent roots
        now = _chrome_time()

        def node(item) -> dict:
            nid = str(next_id[0])
            next_id[0] += 1
            if isinstance(item, Bm):
                return {"id": nid, "name": item.name, "type": "url", "url": item.url, "date_added": now}
            return {
                "id": nid, "name": item.name, "type": "folder", "date_added": now, "date_modified": now,
                "children": [node(c) for c in item.children],
            }

        roots = {}
        for i, (key, title) in enumerate(ROOT_NAMES.items(), start=1):
            roots[key] = {
                "id": str(i), "name": title, "type": "folder", "date_added": now, "date_modified": now,
                "children": [node(c) for c in self.roots[key]],
            }
        # No "checksum": Chromium accepts a file without it.
        return {"roots": roots, "version": 1}

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")
        return path
