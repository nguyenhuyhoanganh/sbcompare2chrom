import json

import yaml

from sbtest.browser.profile import Profile, expand_dotted
from sbtest.browser.version import parse_chromium_version
from sbtest.config import load_config
from sbtest.data import BookmarksSeed, Bm, Folder, files
from sbtest.data.loader import format_data


def test_config_layers(tmp_path, monkeypatch):
    (tmp_path / "default.yaml").write_text(yaml.safe_dump({"browser": {"exe": "", "headless": False},
                                                           "pages": {"scheme": "chrome", "history": "history"}}))
    (tmp_path / "local.yaml").write_text(yaml.safe_dump({"browser": {"exe": "C:/a.exe"}}))
    monkeypatch.setenv("SB_HEADLESS", "true")
    cfg = load_config({"browser.mode": "attach"}, config_dir=tmp_path)
    assert cfg.get("browser.exe") == "C:/a.exe"
    assert cfg.get("browser.headless") is True
    assert cfg.get("browser.mode") == "attach"
    assert cfg.page_url("history") == "chrome://history"
    assert cfg.page_url("internet://x") == "internet://x"


def test_parse_version():
    ua = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/141.0.7390.37 SamsungBrowser/29.0 Safari/537.36"
    assert parse_chromium_version("SamsungInternet/29.0.1.2", ua) == "141.0.7390.37"
    assert parse_chromium_version("HeadlessChrome/120.0.1.2") == "120.0.1.2"
    assert parse_chromium_version("nothing") is None


def test_bookmarks_seed_ids_unique():
    seed = BookmarksSeed().url("A", "http://a").folder("F", [Bm("B", "http://b"), Folder("E")])
    data = seed.to_json()
    ids = []

    def walk(n):
        ids.append(n["id"])
        for c in n.get("children", []):
            walk(c)

    for root in data["roots"].values():
        walk(root)
    assert len(ids) == len(set(ids))
    assert data["roots"]["bookmark_bar"]["children"][1]["children"][0]["url"] == "http://b"


def test_seed_from_dict_and_format():
    raw = {"bookmark_bar": [{"name": "A", "url": "{site}/a"}, {"name": "F", "children": [{"name": "B", "url": "{site}/b"}]}]}
    seed = BookmarksSeed.from_dict(format_data(raw, {"site": "http://h:1"}))
    j = seed.to_json()["roots"]["bookmark_bar"]["children"]
    assert j[0]["url"] == "http://h:1/a" and j[1]["children"][0]["url"] == "http://h:1/b"


def test_profile_prefs_merge(tmp_path):
    p = Profile(tmp_path, "t")
    p.prefs({"download.prompt_for_download": True}).prefs({"download.default_directory": "x"})
    prefs = json.loads((p.default / "Preferences").read_text())
    assert prefs["download"] == {"prompt_for_download": True, "default_directory": "x"}
    assert (p.dir / "First Run").exists()
    assert expand_dotted({"a.b.c": 1}) == {"a": {"b": {"c": 1}}}


def test_png_is_valid(tmp_path):
    f = files.png_file(tmp_path)
    assert f.read_bytes().startswith(b"\x89PNG")
